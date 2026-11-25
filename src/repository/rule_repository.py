"""Преобразование транспортного дерева в связанные реляционные сущности."""
from decimal import Decimal
from sqlmodel import select
from src.core.errors import BusinessRuleError
from src.models.configuration import ConfigurationFunction
from src.models.rule_structure import (
    RuleFunctionClass, RuleOperator, RuleFormalArgument, RuleConstant,
    RuleExpression, RuleActualArgument, RuleFunctionDefinition, RuleConstraintRoot,
)


class RuleRepository:
    def __init__(self, session): self.session = session
    def save(self, row):
        self.session.add(row); self.session.flush(); return row
    def rows(self, model, **filters):
        q = select(model)
        for key, value in filters.items(): q = q.where(getattr(model,key)==value)
        return self.session.exec(q).all()

    def store_expression(self, node):
        kind = node["kind"]
        values = dict(kind=kind)
        if kind == "const":
            value = node["value"]
            typ = "bool" if type(value) is bool else "string" if isinstance(value,str) else "number"
            values["constant_id"] = self.save(RuleConstant(value_type=typ, value_text=str(value))).id
        elif kind == "param": values["parameter_name"] = node["name"]
        elif kind == "op":
            values["operator_id"] = self.rows(RuleOperator,code=node["op"])[0].id
        else:
            values["function_id"] = self.rows(ConfigurationFunction,code=node["function"])[0].id
        row = self.save(RuleExpression(**values))
        args = node.get("args", [])
        pairs = list(args.items()) if isinstance(args,dict) else [(None,v) for v in args]
        for number,(name,child) in enumerate(pairs,1):
            self.save(RuleActualArgument(expression_id=row.id,number=number,name=name,
                                         value_expression_id=self.store_expression(child)))
        return row.id

    def expression(self, node_id, path=()):
        if node_id in path or len(path)>40: raise BusinessRuleError("Цикл или превышение глубины хранимого выражения")
        row = self.session.get(RuleExpression,node_id)
        if row is None: raise BusinessRuleError("Отсутствует узел хранимого выражения")
        if row.kind == "const":
            value=self.session.get(RuleConstant,row.constant_id)
            decoded = value.value_text if value.value_type=="string" else value.value_text=="True" if value.value_type=="bool" else Decimal(value.value_text)
            return {"kind":"const","value":decoded}
        if row.kind == "param": return {"kind":"param","name":row.parameter_name}
        args=sorted(self.rows(RuleActualArgument,expression_id=row.id),key=lambda r:r.number)
        values=[(arg.name,self.expression(arg.value_expression_id,path+(node_id,))) for arg in args]
        if row.kind=="op":
            return {"kind":"op","op":self.session.get(RuleOperator,row.operator_id).code,"args":[v for _,v in values]}
        return {"kind":"call","function":self.session.get(ConfigurationFunction,row.function_id).code,"args":dict(values)}

    def store_function(self, function_id, definition):
        for number,(name,typ) in enumerate(definition["parameters"].items(),1):
            self.save(RuleFormalArgument(function_id=function_id,number=number,name=name,value_type=typ))
        body=definition["body"]
        category="composed"
        if body["kind"]=="op":
            category=self.session.get(RuleFunctionClass,self.rows(RuleOperator,code=body["op"])[0].class_id).code
        cls=self.rows(RuleFunctionClass,code=category)[0]
        self.save(RuleFunctionDefinition(function_id=function_id,class_id=cls.id,
                                         result_type=definition["result"],body_id=self.store_expression(body)))

    def definition(self, function_id):
        definition=self.session.get(RuleFunctionDefinition,function_id)
        if definition is None:
            return self.bom_definition(function_id)
        args=sorted(self.rows(RuleFormalArgument,function_id=function_id),key=lambda r:r.number)
        return {"parameters":{arg.name:arg.value_type for arg in args},"result":definition.result_type,
                "body":self.expression(definition.body_id)}

    def bom_definition(self, function_id):
        """Адаптер тела ДНФ №8 к существующему интерпретатору №7, без копии правил."""
        from src.models.configured_bom import BomFunction, BomConjunction, BomPredicate
        from src.models.parameters import Parameter
        if self.session.get(BomFunction, function_id) is None:
            raise BusinessRuleError("Не задано определение функции")
        parameters, groups = {}, []
        for group in sorted(self.rows(BomConjunction, function_id=function_id), key=lambda r:r.number):
            predicates = []
            for p in sorted(self.rows(BomPredicate, function_id=function_id,
                                      conjunction_number=group.number), key=lambda r:r.number):
                parameter = self.session.get(Parameter,p.parameter_id)
                parameters[parameter.code] = "string" if p.value_text is not None else "number"
                value = p.value_number if p.value_number is not None else (
                    p.enum_value_id if p.enum_value_id is not None else p.value_text)
                predicates.append({"kind":"op", "op":self.session.get(RuleOperator,p.operator_id).code,
                                   "args":[{"kind":"param","name":parameter.code},
                                           {"kind":"const","value":value}]})
            groups.append({"kind":"op","op":"and","args":predicates} if len(predicates)>1 else
                          predicates[0] if predicates else {"kind":"const","value":True})
        body = {"kind":"op","op":"or","args":groups} if len(groups)>1 else (
            groups[0] if groups else {"kind":"const","value":False})
        return {"parameters":parameters,"result":"bool","body":body}

    def constraint(self, constraint_id):
        root=self.session.get(RuleConstraintRoot,constraint_id)
        if root is None: raise BusinessRuleError("Не задан корень ограничения")
        return self.expression(root.expression_id)

    def store_constraint(self, constraint_id, expression):
        self.save(RuleConstraintRoot(constraint_id=constraint_id,expression_id=self.store_expression(expression)))
