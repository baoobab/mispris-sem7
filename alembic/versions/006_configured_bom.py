"""№8: условные позиции BOM и реляционные функции ДНФ."""
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE bom_function (
      function_id integer PRIMARY KEY REFERENCES configuration_function(id));
    CREATE TABLE bom_conjunction (
      function_id integer NOT NULL REFERENCES bom_function(function_id),
      number integer NOT NULL CHECK (number > 0),
      PRIMARY KEY (function_id, number));
    CREATE TABLE bom_predicate (
      function_id integer NOT NULL,
      conjunction_number integer NOT NULL,
      number integer NOT NULL CHECK (number > 0),
      parameter_id integer NOT NULL REFERENCES parameter(id),
      operator_id integer NOT NULL REFERENCES rule_operator(id),
      value_number numeric(18,6), value_text varchar(500),
      enum_value_id integer REFERENCES enum_value(id),
      PRIMARY KEY (function_id, conjunction_number, number),
      FOREIGN KEY (function_id, conjunction_number) REFERENCES bom_conjunction(function_id,number),
      CONSTRAINT ck_bom_predicate_value CHECK (num_nonnulls(value_number,value_text,enum_value_id)=1));
    ALTER TABLE item_bom ADD COLUMN configuration_function_id integer REFERENCES bom_function(function_id);
    DROP INDEX ux_item_bom_active_component;
    CREATE UNIQUE INDEX ux_item_bom_active_component ON item_bom
      (parent_item_id,component_item_id,coalesce(configuration_function_id,0)) WHERE valid_to IS NULL;
    """)
    op.execute("""
    CREATE FUNCTION lab8_eval(p_function integer, p_values jsonb) RETURNS boolean
    LANGUAGE plpgsql STABLE AS $$
    DECLARE c record; p record; actual jsonb; expected jsonb; ok boolean; matched boolean;
    BEGIN
      IF p_function IS NULL THEN RETURN true; END IF;
      IF NOT EXISTS (SELECT 1 FROM bom_function WHERE function_id=p_function) THEN
        RAISE EXCEPTION 'Unknown BOM function %', p_function;
      END IF;
      FOR c IN SELECT number FROM bom_conjunction WHERE function_id=p_function ORDER BY number LOOP
        matched := true;
        FOR p IN SELECT bp.*, ro.code FROM bom_predicate bp JOIN rule_operator ro ON ro.id=bp.operator_id
          WHERE bp.function_id=p_function AND bp.conjunction_number=c.number ORDER BY bp.number LOOP
          actual := p_values -> p.parameter_id::text;
          IF actual IS NULL OR actual='null'::jsonb THEN
            RAISE EXCEPTION 'Missing configuration parameter %', p.parameter_id;
          END IF;
          expected := CASE WHEN p.value_number IS NOT NULL THEN to_jsonb(p.value_number)
            WHEN p.enum_value_id IS NOT NULL THEN to_jsonb(p.enum_value_id) ELSE to_jsonb(p.value_text) END;
          IF jsonb_typeof(actual) <> jsonb_typeof(expected) THEN
            RAISE EXCEPTION 'Wrong configuration parameter type %', p.parameter_id;
          END IF;
          ok := CASE p.code WHEN 'eq' THEN actual=expected WHEN 'ne' THEN actual<>expected
            WHEN 'lt' THEN actual<expected WHEN 'le' THEN actual<=expected
            WHEN 'gt' THEN actual>expected WHEN 'ge' THEN actual>=expected ELSE NULL END;
          IF ok IS NULL THEN RAISE EXCEPTION 'Unsupported predicate operator'; END IF;
          matched := matched AND ok;
        END LOOP;
        IF matched THEN RETURN true; END IF;
      END LOOP;
      RETURN false;
    END $$;

    CREATE FUNCTION lab8_effective(p_item integer, p_at timestamptz)
    RETURNS SETOF item_bom LANGUAGE sql STABLE AS $$
      WITH RECURSIVE chain(id,lvl,path) AS (
        SELECT p_item,0,ARRAY[p_item]
        UNION ALL
        SELECT i.base_item_id,c.lvl+1,c.path||i.base_item_id FROM chain c JOIN item i ON i.id=c.id
        WHERE i.base_item_id IS NOT NULL AND NOT i.base_item_id=ANY(c.path) AND c.lvl<100
      ), chosen AS (
        SELECT DISTINCT ON (b.component_item_id,coalesce(b.configuration_function_id,0)) b.id
        FROM chain c JOIN item_bom b ON b.parent_item_id=c.id
        WHERE b.valid_from<=p_at AND (b.valid_to IS NULL OR b.valid_to>p_at)
          AND (c.lvl=0 OR b.is_base)
        ORDER BY b.component_item_id,coalesce(b.configuration_function_id,0),c.lvl,b.valid_from DESC,b.id DESC
      ) SELECT b.* FROM chosen c JOIN item_bom b ON b.id=c.id WHERE NOT b.is_excluded
        ORDER BY b.order_number,b.component_item_id
    $$;

    CREATE FUNCTION lab8_tree(p_item integer, p_values jsonb, p_at timestamptz,
      p_path integer[] DEFAULT ARRAY[]::integer[], p_norm numeric DEFAULT 1)
    RETURNS TABLE(lvl integer,path integer[],parent_item_id integer,component_item_id integer,
      bom_id integer,function_id integer,quantity numeric,for_quantity numeric,
      unit_quantity_id integer,norm numeric,is_leaf boolean)
    LANGUAGE plpgsql STABLE AS $$
    DECLARE b record; child_norm numeric; current_path integer[]; source_id integer;
    BEGIN
      IF p_item=ANY(p_path) OR cardinality(p_path)>=100 THEN
        RAISE EXCEPTION 'Cycle or maximum BOM depth exceeded: %', p_path||p_item;
      END IF;
      current_path := p_path||p_item;
      SELECT template_id INTO source_id FROM item_configuration WHERE item_id=p_item AND kind='variant';
      source_id := coalesce(source_id,p_item);
      FOR b IN SELECT * FROM lab8_effective(source_id,p_at) LOOP
        IF NOT lab8_eval(b.configuration_function_id,p_values) THEN CONTINUE; END IF;
        child_norm := p_norm*b.quantity/b.for_quantity*coalesce(
          (SELECT coefficient FROM unit_quantity WHERE id=b.unit_quantity_id),1);
        IF b.component_item_id=ANY(current_path) THEN RAISE EXCEPTION 'Cycle in configured BOM'; END IF;
        lvl := cardinality(current_path); path := current_path||b.component_item_id;
        parent_item_id := p_item; component_item_id := b.component_item_id; bom_id := b.id;
        function_id := b.configuration_function_id; quantity := b.quantity; for_quantity := b.for_quantity;
        unit_quantity_id := b.unit_quantity_id; norm := child_norm;
        is_leaf := NOT EXISTS (SELECT 1 FROM lab8_effective(coalesce(
          (SELECT template_id FROM item_configuration WHERE item_id=b.component_item_id AND kind='variant'),
          b.component_item_id),p_at));
        RETURN NEXT;
        RETURN QUERY SELECT * FROM lab8_tree(b.component_item_id,p_values,p_at,current_path,child_norm);
      END LOOP;
    END $$;

    CREATE FUNCTION lab8_norms(p_item integer,p_values jsonb,p_at timestamptz,p_quantity numeric DEFAULT 1)
    RETURNS TABLE(component_item_id integer,total_quantity numeric) LANGUAGE sql STABLE AS $$
      SELECT t.component_item_id,sum(t.norm)*p_quantity FROM lab8_tree(p_item,p_values,p_at) t
      WHERE t.is_leaf GROUP BY t.component_item_id ORDER BY t.component_item_id
    $$;
    """)


def downgrade():
    # Сохраняем определения функций в существующем формате №7 перед удалением тела ДНФ.
    from sqlmodel import Session, select
    from src.models.configured_bom import BomFunction
    from src.repository.rule_repository import RuleRepository
    with Session(bind=op.get_bind(), join_transaction_mode="create_savepoint") as session:
        repo = RuleRepository(session)
        for row in session.exec(select(BomFunction)).all():
            repo.store_function(row.function_id, repo.definition(row.function_id))
        session.commit()
    op.execute("""
      DROP FUNCTION lab8_norms(integer,jsonb,timestamptz,numeric);
      DROP FUNCTION lab8_tree(integer,jsonb,timestamptz,integer[],numeric);
      DROP FUNCTION lab8_effective(integer,timestamptz);
      DROP FUNCTION lab8_eval(integer,jsonb);
      DROP INDEX ux_item_bom_active_component;
      -- Старая схема не допускает альтернативных строк одного компонента.
      -- Закрываем лишние действующие версии, сохраняя их историю.
      UPDATE item_bom SET valid_to=greatest(now(),valid_from) WHERE id IN (
        SELECT id FROM (SELECT id,row_number() OVER (
          PARTITION BY parent_item_id,component_item_id ORDER BY id) n
          FROM item_bom WHERE valid_to IS NULL) ranked WHERE n>1);
      ALTER TABLE item_bom DROP COLUMN configuration_function_id;
      CREATE UNIQUE INDEX ux_item_bom_active_component ON item_bom
        (parent_item_id,component_item_id) WHERE valid_to IS NULL;
      DROP TABLE bom_predicate;
      DROP TABLE bom_conjunction;
      DROP TABLE bom_function;
    """)
