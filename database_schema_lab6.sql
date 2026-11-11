-- Сокращённая схема для диаграмм по заданию №6.
-- 10 новых таблиц из миграции 003 и прежняя таблица item с расширенными методами класса.
-- Поля, ограничения и индексы выбранных таблиц взяты из database_schema.sql.
-- Связи с исключёнными прежними таблицами сохранены как SQL-комментарии возле полей.

/*
Модель средства труда

Новая таблица задания №6.
ТЗ, слайды 3, 5. Спецификация оборудования, инструмента и оснастки.

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

Новая таблица задания №6.
ТЗ, слайды 3, 9–11, 15–17. Классы операций, профессий и ГРЦ различаются полем kind.

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

Новая таблица задания №6.
ТЗ, слайды 12–13. Общие шаги, связи и формулы типового процесса хранятся в definition.

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
Изделие

Расширена логика класса в задании №6. Таблица существовала до задания №6.
ТЗ, слайды 3, 9–11, 19. Изделие объединяет состояния маршрута и расчёты на весь выпуск.

Методы:
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
    UNIQUE (number),
    CONSTRAINT fk_item_base_item FOREIGN KEY(base_item_id) REFERENCES item (id) ON DELETE RESTRICT,
    CONSTRAINT ck_item_not_own_base CHECK (base_item_id IS NULL OR base_item_id <> id)

    -- FOREIGN KEY(item_class_id) REFERENCES item_classifier (id) ON DELETE SET NULL
    -- класс изделия из прежней работы.
    -- CONSTRAINT fk_item_type FOREIGN KEY(item_type_id) REFERENCES enum_value (id)
    -- значение перечисления из прежней работы.
);
CREATE INDEX ix_item_base_item ON item (base_item_id);

/*
Часовая ставка

Новая таблица задания №6.
ТЗ, слайд 3. Стоимость часа труда по профессии и квалификации для калькуляции себестоимости.

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
    FOREIGN KEY(profession_id) REFERENCES technology_class (id)

    -- FOREIGN KEY(qualification_id) REFERENCES enum_value (id)
    -- значение перечисления из прежней работы.
);

/*
Применение типового технологического процесса

Новая таблица задания №6.
ТЗ, слайды 12–13. Параметры конкретного изделия и привязки входных ресурсов
для применения общего типового процесса хранятся в parameters и resources.

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
Групповой рабочий центр

Новая таблица задания №6.
ТЗ, слайды 3, 9–11, 16–17. Место выполнения операции и связь с подразделением предприятия.

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
    FOREIGN KEY(class_id) REFERENCES technology_class (id)

    -- FOREIGN KEY(sxd_id) REFERENCES sxd (id)
    -- подразделение из прежней работы.
);

/*
Инвентарная единица средства труда

Новая таблица задания №6.
ТЗ, слайды 3, 5. Учёт конкретного средства труда по модели, номеру и рабочему центру.

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
Изделие-операция

Новая таблица задания №6.
ТЗ, слайды 9–11, 17. Состояние изделия после операции.
Подтипы «Позиция закупки» и «Позиция техмаршрута» заданы полем kind.
Профессия, квалификация, ГРЦ и нормы времени относятся к производственному подтипу.

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
    FOREIGN KEY(class_id) REFERENCES technology_class (id),
    FOREIGN KEY(work_center_id) REFERENCES work_center (id),
    FOREIGN KEY(profession_id) REFERENCES technology_class (id),
    FOREIGN KEY(template_id) REFERENCES technology_template (id)

    -- FOREIGN KEY(output_unit_id) REFERENCES unit_quantity (id)
    -- единица количества изделия из прежней работы.
    -- FOREIGN KEY(qualification_id) REFERENCES enum_value (id)
    -- значение перечисления из прежней работы.
);
CREATE UNIQUE INDEX ux_technology_operation_output ON technology_operation (item_id) WHERE is_output;

/*
Позиция входного ресурса

Новая таблица задания №6.
ТЗ, слайды 9–11, 17. Связь двух состояний изделий с нормой расхода quantity / for_quantity.

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
    FOREIGN KEY(in_operation_id) REFERENCES technology_operation (id)

    -- FOREIGN KEY(unit_quantity_id) REFERENCES unit_quantity (id)
    -- единица количества изделия из прежней работы.
);
CREATE INDEX ix_technology_input_in_operation_id ON technology_input (in_operation_id);

/*
Требование к средству труда

Новая таблица задания №6.
ТЗ, слайд 3. Требуемая модель оборудования, инструмента или оснастки для операции.

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
