-- Схема PostgreSQL по миграциям 001–003.
-- Перед каждой таблицей указаны название класса и укрупнённые методы приложения.
-- Названия методов из задания №6 сохранены в исходном виде.

/*
Тип документа

Методы:
Создать()
Получить()
Изменить()
Удалить()
*/
CREATE TABLE document_classifier (
    id SERIAL NOT NULL,
    parent_id INTEGER,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(parent_id) REFERENCES document_classifier (id) ON DELETE CASCADE,
    UNIQUE (code)
);

/*
Тип перечисления

Методы:
Создать()
Получить()
Изменить()
Удалить()
*/
CREATE TABLE enum_type (
    id SERIAL NOT NULL,
    code VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (code)
);

/*
Тип хозяйственной операции

Методы:
Создать()
Получить()
Изменить()
Удалить()
ПолучитьДерево()
*/
CREATE TABLE ho_classifier (
    id SERIAL NOT NULL,
    parent_id INTEGER,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(parent_id) REFERENCES ho_classifier (id) ON DELETE CASCADE,
    UNIQUE (code)
);

/*
Класс изделия

Методы:
Создать()
Получить()
Изменить()
Удалить()
*/
CREATE TABLE item_classifier (
    id SERIAL NOT NULL,
    parent_id INTEGER,
    number VARCHAR(50),
    name VARCHAR(255) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(parent_id) REFERENCES item_classifier (id) ON DELETE CASCADE
);

/*
Вид упаковки

Методы:
Создать()
Получить()
Изменить()
Удалить()
*/
CREATE TABLE packaging_type (
    id SERIAL NOT NULL,
    parent_id INTEGER,
    name VARCHAR(255) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(parent_id) REFERENCES packaging_type (id) ON DELETE CASCADE
);

/*
Список прейскурантов

Методы:
Создать()
Получить()
*/
CREATE TABLE pricelist_set (
    id SERIAL NOT NULL,
    parent_id INTEGER,
    PRIMARY KEY (id),
    FOREIGN KEY(parent_id) REFERENCES pricelist_set (id) ON DELETE SET NULL
);

/*
Класс субъекта хозяйственной деятельности

Методы:
Создать()
Получить()
Изменить()
Удалить()
*/
CREATE TABLE sxd_classifier (
    id SERIAL NOT NULL,
    parent_id INTEGER,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(parent_id) REFERENCES sxd_classifier (id) ON DELETE CASCADE,
    UNIQUE (code)
);

/*
Роль субъекта хозяйственной деятельности

Методы:
Создать()
Получить()
Изменить()
Удалить()
*/
CREATE TABLE sxd_role (
    id SERIAL NOT NULL,
    name VARCHAR(255) NOT NULL,
    inverse_id INTEGER,
    PRIMARY KEY (id),
    FOREIGN KEY(inverse_id) REFERENCES sxd_role (id) ON DELETE SET NULL,
    UNIQUE (name)
);

/*
Модель средства труда

Методы:
Создать()
Получить()
*/
CREATE TABLE technology_asset_model (
    id SERIAL NOT NULL,
    code VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    kind VARCHAR(20) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_technology_asset_model_kind CHECK (kind IN ('equipment', 'tool', 'fixture')),
    UNIQUE (code)
);

/*
Класс маршрутной технологии

Методы:
Создать()
Получить()
Изменить()
*/
CREATE TABLE technology_class (
    id SERIAL NOT NULL,
    kind VARCHAR(20) NOT NULL,
    code VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    parent_id INTEGER,
    PRIMARY KEY (id),
    UNIQUE (kind, code),
    CONSTRAINT ck_technology_class_kind CHECK (kind IN ('operation', 'profession', 'work_center')),
    FOREIGN KEY(parent_id) REFERENCES technology_class (id)
);

/*
Типовой технологический процесс

Методы:
Создать()
Получить()
Применить()
*/
CREATE TABLE technology_template (
    id SERIAL NOT NULL,
    code VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    definition JSONB NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (code)
);

/*
Единица измерения

Методы:
Создать()
Получить()
Изменить()
Удалить()
*/
CREATE TABLE unit_simple (
    id SERIAL NOT NULL,
    base_unit_id INTEGER,
    coefficient NUMERIC(18, 6) DEFAULT '1' NOT NULL,
    code VARCHAR(10) NOT NULL,
    name VARCHAR(100) NOT NULL,
    cond_symbol_1 VARCHAR(20),
    cond_symbol_2 VARCHAR(20),
    code_symbol_1 VARCHAR(10),
    code_symbol_2 VARCHAR(10),
    PRIMARY KEY (id),
    FOREIGN KEY(base_unit_id) REFERENCES unit_simple (id) ON DELETE SET NULL,
    UNIQUE (code)
);

/*
Допустимая роль хозяйственной операции

Методы:
Создать()
Получить()
Изменить()
Удалить()
*/
CREATE TABLE available_roles (
    id SERIAL NOT NULL,
    ho_type_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    min_count SMALLINT DEFAULT '0' NOT NULL,
    max_count SMALLINT,
    is_required BOOLEAN DEFAULT 'false' NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(ho_type_id) REFERENCES ho_classifier (id) ON DELETE CASCADE,
    FOREIGN KEY(role_id) REFERENCES sxd_role (id) ON DELETE CASCADE,
    UNIQUE (ho_type_id, role_id)
);

/*
Значение перечисления

Методы:
Создать()
Получить()
Изменить()
Удалить()
*/
CREATE TABLE enum_value (
    id SERIAL NOT NULL,
    enum_type_id INTEGER NOT NULL,
    order_number SMALLINT NOT NULL,
    code VARCHAR(50),
    name VARCHAR(255) NOT NULL,
    numeric_value NUMERIC(18, 6),
    unit_id INTEGER,
    PRIMARY KEY (id),
    FOREIGN KEY(enum_type_id) REFERENCES enum_type (id) ON DELETE CASCADE,
    UNIQUE (enum_type_id, order_number),
    CONSTRAINT fk_enum_value_unit FOREIGN KEY(unit_id) REFERENCES unit_simple (id) ON DELETE SET NULL
);

/*
Хозяйственная операция

Методы:
Создать()
Получить()
Изменить()
Удалить()
Найти()
ПолучитьХарактеристики()
*/
CREATE TABLE ho (
    id SERIAL NOT NULL,
    ho_type_id INTEGER NOT NULL,
    document_number VARCHAR(100),
    op_date DATE NOT NULL,
    amount NUMERIC(18, 2),
    PRIMARY KEY (id),
    FOREIGN KEY(ho_type_id) REFERENCES ho_classifier (id)
);

/*
Упаковка

Методы:
Создать()
Получить()
Изменить()
Удалить()
*/
CREATE TABLE packaging (
    id SERIAL NOT NULL,
    packaging_type_id INTEGER,
    weight NUMERIC(10, 3),
    length NUMERIC(10, 3),
    width NUMERIC(10, 3),
    height NUMERIC(10, 3),
    inner_volume NUMERIC(10, 3),
    PRIMARY KEY (id),
    FOREIGN KEY(packaging_type_id) REFERENCES packaging_type (id) ON DELETE SET NULL
);

/*
Документ

Методы:
Создать()
Получить()
Изменить()
Удалить()
*/
CREATE TABLE document (
    id SERIAL NOT NULL,
    doc_type_id INTEGER NOT NULL,
    ho_id INTEGER,
    reg_number VARCHAR(100),
    doc_date DATE,
    PRIMARY KEY (id),
    FOREIGN KEY(doc_type_id) REFERENCES document_classifier (id),
    FOREIGN KEY(ho_id) REFERENCES ho (id) ON DELETE SET NULL
);

/*
Изделие

Методы:
Создать()
Получить()
Изменить()
Удалить()
Найти()
СоздатьМодификацию()
ПолучитьМодификации()
FIND_TM()
SUM_MR()
TR_TO()
РассчитатьСебестоимость()
*/
CREATE TABLE item (
    id SERIAL NOT NULL,
    item_class_id INTEGER,
    number VARCHAR(50) NOT NULL,
    article VARCHAR(100),
    name VARCHAR(500) NOT NULL,
    item_type_id INTEGER,
    base_item_id INTEGER,
    PRIMARY KEY (id),
    FOREIGN KEY(item_class_id) REFERENCES item_classifier (id) ON DELETE SET NULL,
    UNIQUE (number),
    CONSTRAINT fk_item_type FOREIGN KEY(item_type_id) REFERENCES enum_value (id),
    CONSTRAINT fk_item_base_item FOREIGN KEY(base_item_id) REFERENCES item (id) ON DELETE RESTRICT,
    CONSTRAINT ck_item_not_own_base CHECK (base_item_id IS NULL OR base_item_id <> id)
);
CREATE INDEX ix_item_base_item ON item (base_item_id);

/*
Параметр

Методы:
Создать()
Получить()
Изменить()
Удалить()
*/
CREATE TABLE parameter (
    id SERIAL NOT NULL,
    code VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    param_type_id INTEGER NOT NULL,
    enum_type_id INTEGER,
    unit_simple_id INTEGER,
    PRIMARY KEY (id),
    FOREIGN KEY(param_type_id) REFERENCES enum_value (id),
    FOREIGN KEY(enum_type_id) REFERENCES enum_type (id) ON DELETE SET NULL,
    FOREIGN KEY(unit_simple_id) REFERENCES unit_simple (id) ON DELETE SET NULL,
    UNIQUE (code)
);

/*
Список позиций хозяйственной операции

Методы:
Создать()
ПолучитьПозиции()
*/
CREATE TABLE position_list (
    id SERIAL NOT NULL,
    ho_id INTEGER NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(ho_id) REFERENCES ho (id) ON DELETE CASCADE,
    UNIQUE (ho_id)
);

/*
Субъект хозяйственной деятельности

Методы:
Создать()
Получить()
Изменить()
Удалить()
*/
CREATE TABLE sxd (
    id SERIAL NOT NULL,
    sxd_class_id INTEGER,
    entity_type_id INTEGER NOT NULL,
    name VARCHAR(500) NOT NULL,
    okpo VARCHAR(20),
    PRIMARY KEY (id),
    FOREIGN KEY(sxd_class_id) REFERENCES sxd_classifier (id) ON DELETE SET NULL,
    FOREIGN KEY(entity_type_id) REFERENCES enum_value (id)
);

/*
Часовая ставка

Методы:
Задать()
Получить()
*/
CREATE TABLE technology_labor_rate (
    profession_id INTEGER NOT NULL,
    qualification_id INTEGER NOT NULL,
    hourly_rate NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (profession_id, qualification_id),
    CONSTRAINT ck_technology_labor_rate CHECK (hourly_rate >= 0),
    FOREIGN KEY(profession_id) REFERENCES technology_class (id),
    FOREIGN KEY(qualification_id) REFERENCES enum_value (id)
);

/*
Параметр типа документа

Методы:
Получить()
*/
CREATE TABLE doc_class_parameter (
    id SERIAL NOT NULL,
    doc_type_id INTEGER NOT NULL,
    parameter_id INTEGER NOT NULL,
    display_order SMALLINT DEFAULT '0' NOT NULL,
    min_value NUMERIC(18, 6),
    max_value NUMERIC(18, 6),
    PRIMARY KEY (id),
    FOREIGN KEY(doc_type_id) REFERENCES document_classifier (id) ON DELETE CASCADE,
    FOREIGN KEY(parameter_id) REFERENCES parameter (id) ON DELETE CASCADE,
    UNIQUE (doc_type_id, parameter_id)
);

/*
Параметр типа хозяйственной операции

Методы:
Добавить()
Получить()
Удалить()
*/
CREATE TABLE ho_class_parameter (
    id SERIAL NOT NULL,
    ho_type_id INTEGER NOT NULL,
    parameter_id INTEGER NOT NULL,
    display_order SMALLINT DEFAULT '0' NOT NULL,
    min_value NUMERIC(18, 6),
    max_value NUMERIC(18, 6),
    PRIMARY KEY (id),
    FOREIGN KEY(ho_type_id) REFERENCES ho_classifier (id) ON DELETE CASCADE,
    FOREIGN KEY(parameter_id) REFERENCES parameter (id) ON DELETE CASCADE,
    UNIQUE (ho_type_id, parameter_id)
);

/*
Партия изделия

Методы:
Создать()
Получить()
Удалить()
*/
CREATE TABLE item_batch (
    id SERIAL NOT NULL,
    item_id INTEGER NOT NULL,
    parent_id INTEGER,
    quantity NUMERIC(18, 3) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(item_id) REFERENCES item (id) ON DELETE CASCADE,
    FOREIGN KEY(parent_id) REFERENCES item_batch (id) ON DELETE SET NULL
);

/*
Норма упаковки

Методы:
Добавить()
Получить()
Удалить()
*/
CREATE TABLE packaging_norm (
    id SERIAL NOT NULL,
    item_id INTEGER NOT NULL,
    packaging_id INTEGER NOT NULL,
    quantity NUMERIC(18, 3) NOT NULL,
    gost_number VARCHAR(50),
    PRIMARY KEY (id),
    FOREIGN KEY(item_id) REFERENCES item (id) ON DELETE CASCADE,
    FOREIGN KEY(packaging_id) REFERENCES packaging (id) ON DELETE CASCADE,
    UNIQUE (item_id, packaging_id)
);

/*
Позиция прейскуранта

Методы:
Добавить()
Получить()
Удалить()
*/
CREATE TABLE pricelist (
    id SERIAL NOT NULL,
    pricelist_set_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    article VARCHAR(100),
    price NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(pricelist_set_id) REFERENCES pricelist_set (id) ON DELETE CASCADE,
    FOREIGN KEY(item_id) REFERENCES item (id) ON DELETE CASCADE,
    UNIQUE (pricelist_set_id, item_id)
);

/*
Участник хозяйственной операции

Методы:
Назначить()
Получить()
Снять()
*/
CREATE TABLE sxd_role_in_ho (
    id SERIAL NOT NULL,
    ho_id INTEGER NOT NULL,
    sxd_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(ho_id) REFERENCES ho (id) ON DELETE CASCADE,
    FOREIGN KEY(sxd_id) REFERENCES sxd (id) ON DELETE CASCADE,
    FOREIGN KEY(role_id) REFERENCES sxd_role (id) ON DELETE CASCADE,
    UNIQUE (ho_id, sxd_id, role_id)
);

/*
Применение типового технологического процесса

Методы:
Создать()
ПолучитьПараметры()
*/
CREATE TABLE technology_application (
    item_id INTEGER NOT NULL,
    template_id INTEGER NOT NULL,
    parameters JSONB NOT NULL,
    resources JSONB NOT NULL,
    PRIMARY KEY (item_id),
    FOREIGN KEY(item_id) REFERENCES item (id),
    FOREIGN KEY(template_id) REFERENCES technology_template (id)
);

/*
Единица количества изделия

Методы:
Добавить()
Получить()
Удалить()
*/
CREATE TABLE unit_quantity (
    id SERIAL NOT NULL,
    item_id INTEGER NOT NULL,
    unit_simple_id INTEGER NOT NULL,
    coefficient NUMERIC(18, 6) DEFAULT '1' NOT NULL,
    is_base BOOLEAN DEFAULT 'false' NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(item_id) REFERENCES item (id) ON DELETE CASCADE,
    FOREIGN KEY(unit_simple_id) REFERENCES unit_simple (id) ON DELETE CASCADE,
    UNIQUE (item_id, unit_simple_id)
);

/*
Групповой рабочий центр

Методы:
Создать()
Получить()
Изменить()
*/
CREATE TABLE work_center (
    id SERIAL NOT NULL,
    code VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    class_id INTEGER NOT NULL,
    sxd_id INTEGER NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (code),
    FOREIGN KEY(class_id) REFERENCES technology_class (id),
    FOREIGN KEY(sxd_id) REFERENCES sxd (id)
);

/*
Значение параметра документа

Методы:
Получить()
Изменить()
*/
CREATE TABLE doc_parameter_value (
    id SERIAL NOT NULL,
    document_id INTEGER NOT NULL,
    doc_class_param_id INTEGER NOT NULL,
    value_str VARCHAR(500),
    value_int INTEGER,
    value_real NUMERIC(18, 6),
    value_dt TIMESTAMP WITHOUT TIME ZONE,
    value_enum_id INTEGER,
    PRIMARY KEY (id),
    FOREIGN KEY(document_id) REFERENCES document (id) ON DELETE CASCADE,
    FOREIGN KEY(doc_class_param_id) REFERENCES doc_class_parameter (id) ON DELETE CASCADE,
    FOREIGN KEY(value_enum_id) REFERENCES enum_value (id) ON DELETE SET NULL,
    UNIQUE (document_id, doc_class_param_id)
);

/*
Значение параметра хозяйственной операции

Методы:
Получить()
Изменить()
*/
CREATE TABLE ho_parameter_value (
    id SERIAL NOT NULL,
    ho_id INTEGER NOT NULL,
    ho_class_param_id INTEGER NOT NULL,
    value_str VARCHAR(500),
    value_int INTEGER,
    value_real NUMERIC(18, 6),
    value_dt TIMESTAMP WITHOUT TIME ZONE,
    value_enum_id INTEGER,
    PRIMARY KEY (id),
    FOREIGN KEY(ho_id) REFERENCES ho (id) ON DELETE CASCADE,
    FOREIGN KEY(ho_class_param_id) REFERENCES ho_class_parameter (id) ON DELETE CASCADE,
    FOREIGN KEY(value_enum_id) REFERENCES enum_value (id) ON DELETE SET NULL,
    UNIQUE (ho_id, ho_class_param_id)
);

/*
Позиция хозяйственной операции

Методы:
Создать()
Получить()
Изменить()
Удалить()
*/
CREATE TABLE ho_position (
    id SERIAL NOT NULL,
    position_list_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    quantity NUMERIC(18, 3) NOT NULL,
    price NUMERIC(18, 2),
    unit_quantity_id INTEGER,
    batch_id INTEGER,
    packaging_id INTEGER,
    pricelist_id INTEGER,
    quantity_places INTEGER,
    weight_netto NUMERIC(12, 3),
    total_amount NUMERIC(18, 2) GENERATED ALWAYS AS (quantity * COALESCE(price, 0)) STORED,
    PRIMARY KEY (id),
    FOREIGN KEY(position_list_id) REFERENCES position_list (id) ON DELETE CASCADE,
    FOREIGN KEY(item_id) REFERENCES item (id),
    FOREIGN KEY(unit_quantity_id) REFERENCES unit_quantity (id) ON DELETE SET NULL,
    FOREIGN KEY(batch_id) REFERENCES item_batch (id) ON DELETE SET NULL,
    FOREIGN KEY(packaging_id) REFERENCES packaging (id) ON DELETE SET NULL,
    FOREIGN KEY(pricelist_id) REFERENCES pricelist (id) ON DELETE SET NULL
);

/*
Позиция материальной спецификации

Методы:
Добавить()
Изменить()
Удалить()
ПолучитьСостав()
ПолучитьСоставНаВсюГлубину()
РассчитатьНормыРасхода()
*/
CREATE TABLE item_bom (
    id SERIAL NOT NULL,
    parent_item_id INTEGER NOT NULL,
    component_item_id INTEGER NOT NULL,
    quantity NUMERIC(18, 6) NOT NULL,
    for_quantity NUMERIC(18, 6) DEFAULT '1' NOT NULL,
    unit_quantity_id INTEGER,
    is_base BOOLEAN DEFAULT 'true' NOT NULL,
    is_excluded BOOLEAN DEFAULT 'false' NOT NULL,
    order_number INTEGER DEFAULT '0' NOT NULL,
    valid_from TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    valid_to TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    FOREIGN KEY(parent_item_id) REFERENCES item (id) ON DELETE CASCADE,
    FOREIGN KEY(component_item_id) REFERENCES item (id) ON DELETE RESTRICT,
    FOREIGN KEY(unit_quantity_id) REFERENCES unit_quantity (id) ON DELETE RESTRICT,
    CONSTRAINT ck_item_bom_not_self CHECK (parent_item_id <> component_item_id),
    CONSTRAINT ck_item_bom_quantity_positive CHECK (quantity > 0 OR is_excluded),
    CONSTRAINT ck_item_bom_for_quantity_positive CHECK (for_quantity > 0),
    CONSTRAINT ck_item_bom_valid_period CHECK (valid_to IS NULL OR valid_to >= valid_from)
);
CREATE INDEX ix_item_bom_component ON item_bom (component_item_id);
CREATE INDEX ix_item_bom_parent ON item_bom (parent_item_id);
CREATE UNIQUE INDEX ux_item_bom_active_component ON item_bom (parent_item_id, component_item_id) WHERE valid_to IS NULL;

/*
Инвентарная единица средства труда

Методы:
Создать()
Получить()
Изменить()
Удалить()
*/
CREATE TABLE technology_asset (
    id SERIAL NOT NULL,
    inventory_number VARCHAR(50) NOT NULL,
    model_id INTEGER NOT NULL,
    work_center_id INTEGER NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (inventory_number),
    FOREIGN KEY(model_id) REFERENCES technology_asset_model (id),
    FOREIGN KEY(work_center_id) REFERENCES work_center (id)
);

/*
Позиция технологического маршрута

Методы:
Создать()
Получить()
Изменить()
Удалить()
ПолучитьРесурсы()
ИмпортироватьСостав()
MR_Q()
*/
CREATE TABLE technology_operation (
    id SERIAL NOT NULL,
    item_id INTEGER NOT NULL,
    output_unit_id INTEGER NOT NULL,
    number INTEGER NOT NULL,
    name VARCHAR(255) NOT NULL,
    kind VARCHAR(20) NOT NULL,
    is_output BOOLEAN DEFAULT false NOT NULL,
    class_id INTEGER,
    work_center_id INTEGER,
    profession_id INTEGER,
    qualification_id INTEGER,
    template_id INTEGER,
    template_step_number INTEGER,
    setup_minutes NUMERIC(24, 9) DEFAULT '0' NOT NULL,
    piece_minutes NUMERIC(24, 9) DEFAULT '0' NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (item_id, number),
    CONSTRAINT ck_technology_operation_number CHECK (number > 0),
    CONSTRAINT ck_technology_operation_kind CHECK ((kind = 'purchase' AND class_id IS NULL AND work_center_id IS NULL AND profession_id IS NULL AND qualification_id IS NULL AND setup_minutes = 0 AND piece_minutes = 0) OR (kind = 'production' AND class_id IS NOT NULL AND work_center_id IS NOT NULL AND profession_id IS NOT NULL AND qualification_id IS NOT NULL)),
    CONSTRAINT ck_technology_operation_time CHECK (setup_minutes >= 0 AND piece_minutes >= 0),
    CONSTRAINT ck_technology_operation_template_step CHECK ((template_id IS NULL AND template_step_number IS NULL) OR (template_id IS NOT NULL AND template_step_number IS NOT NULL AND template_step_number > 0)),
    FOREIGN KEY(item_id) REFERENCES item (id),
    FOREIGN KEY(output_unit_id) REFERENCES unit_quantity (id),
    FOREIGN KEY(class_id) REFERENCES technology_class (id),
    FOREIGN KEY(work_center_id) REFERENCES work_center (id),
    FOREIGN KEY(profession_id) REFERENCES technology_class (id),
    FOREIGN KEY(qualification_id) REFERENCES enum_value (id),
    FOREIGN KEY(template_id) REFERENCES technology_template (id)
);
CREATE UNIQUE INDEX ux_technology_operation_output ON technology_operation (item_id) WHERE is_output;

/*
Изменение материальной спецификации

Методы:
Зарегистрировать()
ПолучитьИсторию()
*/
CREATE TABLE item_change (
    id SERIAL NOT NULL,
    item_id INTEGER NOT NULL,
    old_bom_id INTEGER,
    new_bom_id INTEGER,
    change_type_id INTEGER NOT NULL,
    change_date TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    reason VARCHAR(500),
    PRIMARY KEY (id),
    FOREIGN KEY(item_id) REFERENCES item (id) ON DELETE CASCADE,
    FOREIGN KEY(old_bom_id) REFERENCES item_bom (id) ON DELETE SET NULL,
    FOREIGN KEY(new_bom_id) REFERENCES item_bom (id) ON DELETE SET NULL,
    FOREIGN KEY(change_type_id) REFERENCES enum_value (id)
);
CREATE INDEX ix_item_change_item ON item_change (item_id);

/*
Позиция входного ресурса

Методы:
ЗадатьНорму()
Получить()
Удалить()
*/
CREATE TABLE technology_input (
    out_operation_id INTEGER NOT NULL,
    in_operation_id INTEGER NOT NULL,
    quantity NUMERIC(24, 9) NOT NULL,
    for_quantity NUMERIC(24, 9) DEFAULT '1' NOT NULL,
    unit_quantity_id INTEGER NOT NULL,
    PRIMARY KEY (out_operation_id, in_operation_id),
    CONSTRAINT ck_technology_input_not_self CHECK (out_operation_id <> in_operation_id),
    CONSTRAINT ck_technology_input_quantity CHECK (quantity > 0 AND for_quantity > 0),
    FOREIGN KEY(out_operation_id) REFERENCES technology_operation (id) ON DELETE CASCADE,
    FOREIGN KEY(in_operation_id) REFERENCES technology_operation (id),
    FOREIGN KEY(unit_quantity_id) REFERENCES unit_quantity (id)
);
CREATE INDEX ix_technology_input_in_operation_id ON technology_input (in_operation_id);

/*
Требование к средству труда

Методы:
Задать()
Получить()
Удалить()
*/
CREATE TABLE technology_tool_requirement (
    operation_id INTEGER NOT NULL,
    model_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    PRIMARY KEY (operation_id, model_id),
    CONSTRAINT ck_technology_tool_requirement_quantity CHECK (quantity > 0),
    FOREIGN KEY(operation_id) REFERENCES technology_operation (id) ON DELETE CASCADE,
    FOREIGN KEY(model_id) REFERENCES technology_asset_model (id)
);
