我会先把你刚刚这套 Q1–Q7 的回答整理成一份更“面向 AI 工厂”的正式对接说明文档，尽量保持原意不改逻辑，只做措辞收紧和结构化，方便你直接拷贝过去。SQL 草案我们可以放在这份说明之后的下一步来写。

下面是按你刚才 Q1–Q7 回答整理后的 **「给 AI 工厂的正式确认 & 建议说明」**，你可以几乎原样发给他们。  
（内容基本不改逻辑，只稍微收紧措辞、优化结构。）

---

# beibei 工单采集项目 – 表结构与字段设计确认说明

本文是对前期沟通中 AI 工厂提出问题的集中回应，用于指导在 `rag_db` 中创建 beibei 相关表结构，并约定第一阶段的数据写入范围。

---

## Q1. `order_id` / `service_id` 的关系与唯一性

- **业务假设**  
  基于当前贝壳商户后台页面表现：  
  - 一条列表“卡片”通常对应一组 “订单 + 服务单”；  
  - 在没有更多反例前，我们按 **一单可多服务单** 的上限来设计结构，以保证后续可扩展。

- **唯一性设计建议**
  - 表内主键：  
    - `id BIGSERIAL PRIMARY KEY`（内部自增主键）
  - 业务唯一约束：  
    - 建议使用 **联合唯一 `(order_id, service_id)`**  
    - 如果某条记录没有 `service_id`，则为 `(order_id, NULL)`，可依业务约定避免重复写入。
  - 这样比仅以 `order_id` 唯一更稳妥，也兼容未来出现“一单多服务单”的可能。

> **结论**：主键使用 `id`，并建立 `(order_id, service_id)` 联合唯一索引。

---

## Q2. 状态字段拆分（status）设计

- 页面上状态以一段中文文案展示（如“服务中”“服务完成”“挂起中”等），同时还有服务类型等信息。
- 为避免在采集端内置过多业务规则，建议在主表中采用以下设计：

1. **状态字段**
   - `status_text TEXT`：**原文状态字符串**（必填）  
   - `status_code TEXT`：标准化状态码（可选，前期允许为空，如 `SERVICE_IN_PROGRESS`）

2. “订单状态 / 服务状态”不在采集端强行拆分，后续由 AI 工厂在数仓/服务侧通过 `status_text` 做统一映射和标准化。

> **结论**：第一阶段只保证 `status_text` 必填，同时预留 `status_code` 用于后续标准化。

---

## Q3. JSON / JSONB 类型与表名前缀

- **JSON 字段类型**
  - 对于 `category_tags`、`extra_json` 等扩展字段，建议在 Postgres 中使用：  
    - 类型：`JSONB`  
    - 方便后续做键级查询、索引和数据挖掘。
  - 采集端会以 JSON 格式写入（如 Python dict → JSON 字符串 → `jsonb`）。

- **表名前缀**
  - `rag_db` 中会承载多来源数据。为便于区分，建议 beibei 相关表统一增加前缀：  
    - 主表：`beibei_ticket_items`  
    - 子表：`beibei_ticket_details`  
    - 子表：`beibei_ticket_goods`  
    - 子表：`beibei_ticket_service_process`  
    - 子表：`beibei_ticket_media`

> **结论**：JSON 类字段统一使用 `jsonb`；beibei 相关表统一使用 `beibei_` 前缀。

---

## Q4. 客户 / 服务者字段与脱敏策略

- 页面的客户手机号等信息本身已做脱敏（如 `137****5975`），采集端 **不会做任何反脱敏**。
- 字段建议如下：

- 客户侧：
  - `customer_name_mask TEXT`（如“马某某”）  
  - `customer_phone_mask TEXT`（如 `137****5975`）

- 服务者 / 认领人：
  - `service_provider_name TEXT`  
  - `service_provider_phone_mask TEXT`（如果页面上有，否则为空）  
  - `receiver_name TEXT`（认领人姓名）

> **结论**：仅存“页面已脱敏”的内容，统一使用 `*_mask` 命名，不做反脱敏处理。

---

## Q5. `beibei_ticket_goods`：商品 / 服务是否分表

- 页面中“下单商品”“服务项目”等区域本质上都是多行明细，结构类似，只是语义有差异。
- 为减少表数量并保持灵活性，建议：

1. 只建一个明细表：`beibei_ticket_goods`  
2. 在表中增加字段 `line_type TEXT`：  
   - 取值示例：`'goods'`, `'service'`, `'other'`
3. 其余字段统一：  
   - `item_name`, `item_category`, `quantity`, `price`, `amount`, `remark` 等

> **结论**：第一版只使用一个明细表，通过 `line_type` 区分商品/服务，后续如有必要再拆分。

---

## Q6. `beibei_ticket_details` 是否一单一房源（1:1）

- 从当前详情页截图看，一条订单对应一套房源/一条详情记录，暂未发现“一单多房源”的情况。
- 为简化设计，第一阶段按 **1:1** 关系处理：

  - `beibei_ticket_details`：
    - `id BIGSERIAL PRIMARY KEY`  
    - `order_id TEXT UNIQUE REFERENCES beibei_ticket_items(order_id)`  
    - 其他字段包括：项目/房源名称、地址、户型/面积信息、下单渠道、费用摘要等。

- 若后续业务上出现“一单多房源”：
  - 可以去掉 `order_id` 上的唯一约束，  
  - 并增加 `house_index INT` 等字段区分多套房源。

> **结论**：当前按“一单一详情记录（1:1）”设计，未来如有业务变化再扩展。

---

## Q7. 第一阶段采集端必须落地的字段范围（最小字段集）

为保证迭代节奏，建议第一阶段只强制落地一个**最小字段集**，其余字段先在表中预留，有就写、没有允许为空。

### 7.1 `beibei_ticket_items` 第一阶段必填字段

- `order_id TEXT`  
- `service_id TEXT`（如列表页稳定可见；字段会存在，实际是否必填取决于页面情况）  
- `title TEXT`（工单标题）  
- `status_text TEXT`（原文状态）  
- `page_index INT`（抓取时的列表页序号，从 1 开始）  
- `row_index INT`（该页中的行号，从 1 开始）  
- `capture_ts TIMESTAMPTZ`（抓取时间）  
- `ocr_engine TEXT`（如 `qwen3-vl`、`deepseek-ocr` 等）  
- `signature TEXT`（如 `sha1(order_id || '|' || coalesce(service_id, ''))`）

> 其他字段（创建时间、预约时间、参与人、标签、`extra_json` 等）会在表结构中预留，采集端会 **逐步补充**，不作为第一阶段的硬性要求。

### 7.2 详情页四个子表

- `beibei_ticket_details`  
- `beibei_ticket_goods`  
- `beibei_ticket_service_process`  
- `beibei_ticket_media`  

第一阶段仅由 AI 工厂根据上述设计 **先创建表结构**，不要求采集端立即写入。  
采集端将在第二阶段实现“逐条点击详情页 + 截图 + 识别”的工作流后，再对这些子表进行写入对接.

---

## 通道与架构复用约定

- 在数据库与基础设施层面，beibei 项目优先复用 AI 工厂现有能力，包括：Postgres 集群、RAG 相关组件、任务编排与监控告警体系等，不另起一套独立架构。  
- 在逻辑隔离层面，通过以下方式为 beibei 建立“独立通道”：  
  - 数据库层：使用统一集群 + `beibei_` 表前缀（或独立 schema，如 `schema = beibei`），使 beibei 数据与其他数据源在逻辑上可分、在物理上可共用。  
  - 任务与告警层：如需对 beibei 的采集任务、入库任务建立独立看板或告警通道，可在现有任务/告警系统内增加 beibei 专用的任务组/告警组，而不重新搭建新系统。  
- 整体目标是在保证 beibei 有清晰“接入通道”的前提下，最大化复用 AI 工厂既有基础设施与运维体系，降低维护成本。

---

## 总结

- beibei 侧负责：  
  - 屏幕驱动抓取 + OCR 结构化；  
  - 将列表页识别出的工单信息写入 `beibei_ticket_items`，遵守 `(order_id, service_id)` 联合唯一约束。  

- AI 工厂侧负责：  
  - 在 `rag_db` 中创建 `beibei_` 前缀的主表与子表；  
  - 字段中对扩展信息采用 `jsonb`；  
  - 接受“第一阶段仅写入最小字段集”的策略，后续迭代逐步补全字段与详情子表数据。

如果这份说明没有问题，AI 工厂即可按此完成建表工作，后续我们会再对接具体的 Upsert SQL 模板与写入规范。  

---  

如果你需要，我下一步可以在这个基础上直接补一份 **完整建表 SQL 草案（CREATE TABLE + 索引）**，你可以一起打包给他们.

---  

## 附录：SQL 建表草案（示例）

以下为基于上述约定整理的建表 SQL 草案，供 AI 工厂侧参考实施。实际执行时可根据内部规范（如 schema 名称、表空间、索引命名规则等）做适当调整。

> 说明：示例中默认使用统一库 + `beibei_` 表前缀。如采用独立 schema（例如 `beibei`），可相应调整为 `beibei.beibei_ticket_items` 等形式。

```sql
-- 主表：beibei_ticket_items
CREATE TABLE IF NOT EXISTS beibei_ticket_items (
    id                      BIGSERIAL PRIMARY KEY,
    order_id                TEXT        NOT NULL,
    service_id              TEXT,

    -- 列表页可见基础信息
    title                   TEXT,
    order_type              TEXT,
    status_text             TEXT        NOT NULL,
    status_code             TEXT,
    category_tags           JSONB,

    -- 时间类字段
    created_time            TIMESTAMPTZ,
    accepted_time           TIMESTAMPTZ,
    expected_time_raw       TEXT,
    expected_time_start     TIMESTAMPTZ,
    expected_time_end       TIMESTAMPTZ,

    -- 参与人/客户信息（已脱敏）
    service_provider_name       TEXT,
    service_provider_phone_mask TEXT,
    receiver_name               TEXT,
    customer_name_mask          TEXT,
    customer_phone_mask         TEXT,

    -- 状态/备注简要
    phone_contact_status    TEXT,
    remark_summary          TEXT,

    -- 抓取元数据
    page_index              INT,
    row_index               INT,
    capture_ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_image            TEXT,
    ocr_engine              TEXT,
    signature               TEXT,

    -- 预留扩展
    extra_json              JSONB,

    CONSTRAINT beibei_ticket_items_uq_order_service
        UNIQUE (order_id, service_id)
);

-- 常用查询索引示例
CREATE INDEX IF NOT EXISTS idx_beibei_ticket_items_order_id
    ON beibei_ticket_items (order_id);

CREATE INDEX IF NOT EXISTS idx_beibei_ticket_items_service_id
    ON beibei_ticket_items (service_id);

CREATE INDEX IF NOT EXISTS idx_beibei_ticket_items_capture_ts
    ON beibei_ticket_items (capture_ts DESC);
```

```sql
-- 子表 1：工单详情（1:1）
CREATE TABLE IF NOT EXISTS beibei_ticket_details (
    id              BIGSERIAL PRIMARY KEY,
    order_id        TEXT NOT NULL,

    -- 房源/项目信息
    project_name    TEXT,
    house_name      TEXT,
    address         TEXT,
    room_info       TEXT,

    -- 下单/渠道信息
    order_channel   TEXT,

    -- 费用等摘要信息，可后续扩展为结构化
    fee_info        JSONB,

    extra_json      JSONB,

    CONSTRAINT beibei_ticket_details_uq_order
        UNIQUE (order_id),

    CONSTRAINT beibei_ticket_details_fk_order
        FOREIGN KEY (order_id)
        REFERENCES beibei_ticket_items(order_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_beibei_ticket_details_order_id
    ON beibei_ticket_details (order_id);
```

```sql
-- 子表 2：商品 / 服务项目明细
CREATE TABLE IF NOT EXISTS beibei_ticket_goods (
    id              BIGSERIAL PRIMARY KEY,
    order_id        TEXT NOT NULL,

    line_type       TEXT,           -- goods / service / other
    item_name       TEXT,
    item_category   TEXT,
    quantity        NUMERIC,
    price           NUMERIC,
    amount          NUMERIC,
    remark          TEXT,

    extra_json      JSONB,

    CONSTRAINT beibei_ticket_goods_fk_order
        FOREIGN KEY (order_id)
        REFERENCES beibei_ticket_items(order_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_beibei_ticket_goods_order_id
    ON beibei_ticket_goods (order_id);
```

```sql
-- 子表 3：服务过程 / 状态流转
CREATE TABLE IF NOT EXISTS beibei_ticket_service_process (
    id              BIGSERIAL PRIMARY KEY,
    order_id        TEXT NOT NULL,

    event_time      TIMESTAMPTZ,
    event_type      TEXT,       -- 原文事件类型，如“创建工单”“服务者接单”等
    event_type_code TEXT,       -- 可选标准化枚举，如 CREATED / ASSIGNED
    operator        TEXT,       -- 操作人（system / 某客服 / 服务者等）
    comment         TEXT,
    raw_text        TEXT,       -- 完整原文记录，防止信息丢失

    extra_json      JSONB,

    CONSTRAINT beibei_ticket_service_process_fk_order
        FOREIGN KEY (order_id)
        REFERENCES beibei_ticket_items(order_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_beibei_ticket_service_process_order_id
    ON beibei_ticket_service_process (order_id);

CREATE INDEX IF NOT EXISTS idx_beibei_ticket_service_process_event_time
    ON beibei_ticket_service_process (event_time DESC);
```

```sql
-- 子表 4：图片 / 附件
CREATE TABLE IF NOT EXISTS beibei_ticket_media (
    id              BIGSERIAL PRIMARY KEY,
    order_id        TEXT NOT NULL,

    media_type      TEXT,       -- before / after / other
    image_slot      INT,        -- 第几张
    local_path      TEXT,       -- 本地保存路径（如有）
    source_image    TEXT,       -- 对应原始截图文件名
    remote_url      TEXT,       -- 如未来上传到对象存储，可在此存访问地址
    caption         TEXT,       -- 模型识别的图片说明（可选）

    extra_json      JSONB,

    CONSTRAINT beibei_ticket_media_fk_order
        FOREIGN KEY (order_id)
        REFERENCES beibei_ticket_items(order_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_beibei_ticket_media_order_id
    ON beibei_ticket_media (order_id);
```