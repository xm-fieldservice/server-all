# Agent Role System v0.1

## 角色矩阵

| 角色 | 核心职责 | 关键能力 | 产出 |
|------|----------|----------|------|
| **PM** | 指挥、判断、决策 | 形势分析、策略制定、任务分解 | 指令、SOP、新工具 |
| **书记员** | 信息采集、归纳、检索 | 异步监听、信息提取、分发 | 结构化知识、RAG更新 |
| **内务Agent** | 流程执行、工作流驱动 | 定时任务、状态跟踪、节点召集 | 流程完成、状态更新 |
| **计划员** | 策略更新、阈值监控 | 变化检测、规则引擎、计划生成 | 新计划、新策略 |
| **调度员** | 任务分发、资源分配 | 负载均衡、优先级排序 | 任务路由 |
| **培训员** | 知识传递、能力建设 | 教程生成、学习追踪 | 培训材料 |

---

## 知识层级体系

知识有不同的**抽象层级**，高级知识往往来自对低级知识的归纳总结。

### 世界知识之塔

```
                    ▲
                   ╱ ╲
                  ╱   ╲
                 ╱ 智慧 ╲      【战略层】认知、判断、决策
                ╱─────────╲
               ╱   知识    ╲    【战术层】方法、模式、经验
              ╱─────────────╲
             ╱     信息      ╲  【执行层】数据、事实、状态
            ╱─────────────────╲
           ╱       数据        ╗ 【基础层】原始记录、日志
          ╱─────────────────────╲
```

### 知识产生机制

知识不只是"记录"，更是**逐层提炼**的结果：

```
原始素材（Raw）
    ↓ 【第一层加工：信息提取】
结构化信息（提取关键、分类、标签）
    ↓ 【第二层加工：知识关联】
方法论（模式、经验、规则）
    ↓ 【第三层加工：智慧生成】
哲学/认知（判断、决策、策略）
```

> **关键洞察**：高级知识不是凭空产生的，而是从原始素材中**归纳**出来的。同时，这个过程是可逆的——好的实践会沉淀为方法论，方法论可能晋升为普适哲学。

### 知识流动

- **向下传导**：哲学/认知指导方法论，方法论指导执行
- **向上归纳**：实践案例沉淀为方法论，方法论抽象为认知

---

## 知识聚焦体系

每个角色有**职责聚焦**——同一份知识，对不同角色有不同权重：

- **core (核心)**: 该角色必须精通、全权负责
- **reference (参考)**: 需要了解，但非专长
- **base (基础)**: 所有人都需要的基础信息

> 注意：这不是权限控制。同一份知识，PM可以看，Coder也可以看，但"看多深"取决于角色职责。

### 书记员的知识主框架

书记员负责维护的知识主框架包含四层：

1. **宪法级知识** - 业界公认方法论（PMBOK、敏捷等）
2. **系统字典** - 基于宪法级的通用概念
3. **业务字典** - 私域知识、行业经验、内部约定
4. **项目字典** - 项目特有概念

> 这不是书记员私有的框架，而是项目的公共知识基础设施。所有Agent共享使用。

### 知识冲突处理规则

当Agent遇到的信息与系统知识/规则冲突时：

```yaml
# 冲突处理策略（Agent可自主选择）
conflict_resolution:
  # 策略1：停下来核实
  - name: 核实确认
    trigger: 冲突涉及关键决策或安全相关
    action: 找书记员和PM确认
    
  # 策略2：自动退让
  - name: 退让给系统规则
    trigger: 冲突不涉及关键决策
    action: 自动遵循宪法级/系统字典的规则
```

两种策略都是**可接受的**，由Agent根据具体情况自主判断。

```yaml
# Agent的"知识态度"示例
# 当Coder遇到代码规范与"业务惯例"冲突时
example:
  situation: "代码规范说要用 camelCase，但业务代码都用 snake_case"
  option_1: "停下来找书记员确认哪个是标准"
  option_2: "遵循系统级代码规范，自动改用 camelCase"
  both_acceptable: true
```

---

## 宪法级知识框架

任何项目在建立知识库时，必须先**引用和声明**宪法级知识框架。

> 宪法级知识 = 业界公认的通用方法论框架，作为项目知识库的基础

### 框架清单

```yaml
# 宪法级知识框架（按需引用）
constitutional_frameworks:
  # 项目管理 - PMBOK
  - name: PMBOK
    source: PMI
    description: 项目管理知识体系
    scope: 项目全生命周期管理
    key_concepts: [范围, 时间, 成本, 质量, 资源, 沟通, 风险, 采购, 干系人, 整合]
    
  # 软件工程 - IEEE/ISO
  - name: 软件工程
    source: IEEE / ISO 25010
    description: 软件开发方法论
    scope: 需求、设计、开发、测试、部署
    
  # 敏捷 - Scrum/Kanban
  - name: 敏捷开发
    source: Scrum Guide / Kanban
    description: 迭代式开发框架
    scope: 冲刺、迭代、看板
    
  # 质量管理 - ISO 9001
  - name: 质量管理
    source: ISO 9001
    description: 质量管理体系
    scope: 质量策划、质量保证、质量控制、质量改进
    
  # 安全 - ISO 27001
  - name: 信息安全
    source: ISO 27001
    description: 信息安全管理体系
    scope: 机密性、完整性、可用性
```

### 项目中的引用方式

```yaml
# 在 project.yaml 中声明
constitutional:
  - framework: PMBOK
    version: "7th"
    emphasis: [范围, 风险, 干系人]  # 本项目重点关注的领域
    
  - framework: 敏捷开发
    variant: Scrum
    emphasis: [冲刺, 每日站会, 回顾会]
    
  - framework: 软件工程
    emphasis: [需求分析, 架构设计, 单元测试]
```

### 宪法级知识的位置

```
项目知识库/
├── 00-constitution/           # 宪法级知识引用
│   ├── pmbok-core.yaml        # PMBOK核心概念
│   ├── agile-framework.yaml   # 敏捷框架
│   └── quality-standards.yaml # 质量标准
│
├── 01-system-dictionary/       # 系统字典（基于宪法框架的通用概念）
│   ├── project-management/     # 项目管理概念
│   └── ...
│
├── 02-project-dictionary/      # 项目字典（项目特有概念）
│   ├── agriculture/            # 农业领域
│   └── this-project/          # 本项目特有
│
└── 03-knowledge/               # 实际知识内容
```

---

## 业务知识框架

与宪法级知识框架对应，**业务知识框架**是项目特有的、私域的、实用的知识体系。

### 特点

| 特征 | 宪法级知识框架 | 业务知识框架 |
|------|---------------|-------------|
| 来源 | 业界公认方法论 | 从业者自定义 |
| 系统性 | 完整成体系 | 碎片化、实用优先 |
| 稳定性 | 相对稳定，久经考验 | 变化快，生命周期短 |
| 可查找性 | 公开出版物、互联网可查 | 私域知识、口述经验 |
| 典型内容 | PMBOK、Scrum指南 | 内部流程、约定俗成 |

### 业务知识框架的内容

```yaml
# 业务知识框架示例
business_frameworks:
  # 内部流程规范
  - name: 内部审批流程
    source: 企业内部规定
    content: [请假审批, 采购审批, 报销流程]
    lifecycle: stable  # 相对稳定
    
  # 行业经验
  - name: 农业项目经验
    source: 资深农艺师口述
    content: [作物轮作, 季节性管理, 气象应对]
    lifecycle: evolving  # 持续更新
    
  # 内部约定
  - name: 代码规范
    source: 团队实践
    content: [命名规则, 提交规范, Review流程]
    lifecycle: stable
    
  # 临时规则
  - name: 紧急响应规则
    source: 突发情况总结
    content: [突发事件分类, 响应级别, 通知链]
    lifecycle: temporary  # 可能很快失效
```

### 知识生命周期

```
新业务知识产生
    ↓
沉淀期（频繁更新）→ 稳定期（相对固定）
    ↓                      ↓
可能消亡            升级为宪法级知识
                         ↓
                   移动到系统字典
```

> 好的业务知识会慢慢提炼成系统级知识，差的业务知识会随业务变化而消亡

### 业务知识框架的位置

```
项目知识库/
├── 00-constitution/           # 宪法级知识引用
│
├── 01-system-dictionary/       # 系统字典
│
├── 02-project-dictionary/      # 项目字典
│
├── 03-knowledge/               # 实际知识内容
│   ├── 10-business/            # 业务知识框架（私域）
│   │   ├── internal-processes/ # 内部流程
│   │   ├── industry-experience/ # 行业经验
│   │   ├── conventions/        # 约定俗成
│   │   └── temporary-rules/    # 临时规则
│   │
│   └── 20-working/             # 工作记录
│       ├── meeting-notes/      # 会议记录
│       ├── decisions/          # 决策记录
│       └── lessons-learned/    # 经验教训
```

### 业务知识的采集

- **日常文档**：内部Wiki、邮件、聊天记录
- **口述记录**：访谈、讨论、会议纪要
- **工作提炼**：从实际工作中总结的经验
- **外部参考**：行业报告、竞争对手分析（需脱敏）

---

## 项目字典

书记员在建立知识库时，必须先建立**项目字典**——统一项目内的概念体系。

### 字典结构

```
字典/
├── 系统字典/          # 放之四海而皆准，在项目内重新声明
│   ├── 项目管理/      # 通用项目管理概念（基于PMBOK）
│   ├── 质量管理/      # 通用质量概念
│   ├── 敏捷开发/      # 通用开发方法论
│   └── ...
│
├── 业务字典/          # 业务知识框架（私域、实用）
│   ├── 内部流程/      # 企业内部规定
│   ├── 行业经验/      # 行业特定经验
│   └── 约定俗成/      # 团队内部约定
│
└── 项目字典/          # 项目特有概念
    ├── 农业项目/       # 农业领域专有名词
    ├── 项目边界/       # 本项目的范围定义
    └── ...
```

### 系统字典示例

> PMBOK核心概念 - 宪法级知识，必须引用和声明

```yaml
# 系统字典 - PMBOK核心（精简版）
system_dictionary:
  pmbok_core:
    - name: 项目范围
      definition: 项目所包含的全部工作内容和交付成果
      importance: 必须先确定范围，才能开展工作
      related: [WBS, 需求, 边界]
      
    - name: 项目时间
      definition: 项目的进度计划和里程碑安排
      related: [进度, 里程碑, 工期]
      
    - name: 项目成本
      definition: 项目所需的资源投入和预算控制
      related: [预算, 资源, 成本]
      
    - name: 项目质量
      definition: 项目满足需求的程度和标准
      related: [质量标准, 验收, QA]
      
    - name: 项目资源
      definition: 支撑项目完成的人力、物资、设备等
      related: [团队, 设备, 材料]
      
    - name: 项目沟通
      definition: 项目信息的收集、制作、分发和存档
      related: [报告, 会议, 文档]
      
    - name: 项目风险
      definition: 可能发生的不确定事件及其应对
      related: [风险识别, 应对策略, 监控]
      
    - name: 项目采购
      definition: 从外部获取产品或服务
      related: [供应商, 合同, 采购]

  # 项目治理核心
  governance:
    - name: 项目章程
      definition: 正式批准项目存在的文件，授权PM动用资源
      related: [授权, 发起人]
      
    - name: 需求追踪矩阵
      definition: 链接需求与可交付成果的文档
      related: [需求, 验收标准]
      
    - name: 变更控制
      definition: 对范围/进度/成本的变更进行评审和决策的流程
      related: [变更请求, CCB]

  # 精简版项目要素
  essentials:
    - name: 项目三约束
      definition: 范围-时间-成本，三者相互影响
      
    - name: 项目四阶段
      definition: 启动-规划-执行-监控-收尾（五大过程组）
      
    - name: 干系人
      definition: 受项目影响或能影响项目的人
      related: [发起人, 客户, 团队, 用户]

  # 通用项目管理概念
  project_management:
    - name: 项目边界
      definition: 项目的范围定义，明确包含和不包含的内容
      synonyms: [范围, Scope]
      
    - name: 项目背景
      definition: 项目发起的原因、业务场景、现状问题
      synonyms: [背景, Context, 现状]
      
    - name: 项目团队
      definition: 参与项目的所有人员及其角色分工
      synonyms: [团队, Team]
      
    - name: 里程碑
      definition: 项目中的关键节点，通常是交付物完成的时点
      synonyms: [Milestone, 关键节点]
      
    - name: 风险
      definition: 可能对项目目标产生正面或负面影响的不确定事件
      synonyms: [Risk, 不确定性]

  balanced_scorecard:
    - name: 平衡计分卡
      definition: 从财务、客户、内部流程、学习成长四个维度衡量组织绩效
      dimensions: [财务, 客户, 内部流程, 学习成长]
```

### 项目字典示例

```yaml
# 项目字典 - 农业项目
project_dictionary:
  agriculture:
    - name: 作物生长周期
      definition: 从播种到收获的完整时间过程
      phases: [播种, 发芽, 生长, 开花, 成熟, 收获]
      
    - name: 灌溉周期
      definition: 农田灌溉的时间安排和水量控制
      factors: [土壤湿度, 作物需求, 气候条件]
      
    - name: 病虫害防治
      definition: 作物病虫害的预防和治理措施
      methods: [生物防治, 化学防治, 物理防治]

  # 本项目特有概念
  this_project:
    - name: 智慧农业平台
      definition: 本项目开发的核心系统，用于监控和管理农田
      
    - name: 大棚编号规则
      definition: A-01, A-02... 其中字母代表区域，数字代表编号
      
    - name: 传感器数据
      definition: 来自农田传感器的监测数据，包括温度、湿度、光照等
```

### 字典维护

- **来源**：不是自己创设，而是从项目文档、需求、沟通中**提取和声明**
- **更新**：书记员发现新概念时，先记录，定期与PM确认后纳入字典
- **使用**：所有Agent在沟通时必须使用字典中的标准术语

---

## 角色详解

### 1. PM (项目经理)

```yaml
role: PM
name: Project Manager
alias: 指挥官

knowledge:
  core:        # 核心（精通）
    - role/pm/strategies/          # 战略思考
    - role/pm/dictionary/          # PMBOK核心概念（宪法级）
    - vault/decisions/             # 决策库
    - vault/sops/                   # SOP库
  reference:  # 参考（了解）
    - vault/code/                # 代码实现
    - vault/workflows/          # 工作流细节
  base:       # 基础（常识）
    - project.yaml
    - AGENTS.md

capabilities:
  - 形势判断: 综合信息做出决策
  - 任务生成: 从问题/需求生成具体任务
  - 策略制定: 定义方法和规则
  - SOP创建: 把经验固化为流程
  - 工具开发: 创建新Agent/工具

tools:
  # 读取
  - read, glob, grep
  
  # 分析
  - codesearch, websearch
  
  # 输出
  - write, edit
  
  # 执行
  - bash, task

autonomy: high  # 可完全自主决策

behavior:
  - 主动采集各方信息
  - 定期审视全局状态
  - 识别模式，生成SOP
  - 设计新工具/新Agent
```

### 2. 书记员 (信息管理员)

```yaml
role: Clerk
name: 信息管理员 / 书记员
alias: 知识枢纽

knowledge:
  core:
    - role/clerk/dictionary/        # 项目字典（核心职责）
    - role/clerk/index/             # 信息索引
    - vault/qa/                     # Q&A知识库
    - vault/raw/                    # 原始信息
  reference:
    - vault/code/                 # 了解技术背景
    - vault/decisions/            # 了解决策背景
  base:
    - project.yaml
    - 01-inbox/

capabilities:
  - 信息源接入: 管理各种数据采集通道（API/Webhook/数据库/文件）
  - 信息采集: 从多源(企微/飞书/邮件/文档)异步拉取
  - 信息归纳: 提取关键、分类、标签
  - 知识检索: RAG查询、按需推送
  - 变化检测: 识别新模式、异常
  - 知识分层: 将知识归类到数据/信息/知识/智慧层级

tools:
  - read, glob, grep
  - webfetch, websearch
  - write, edit
  - bash (API调用)

autonomy: high  # 异步自动运行

behavior:
  - 7x24小时监听信息源
  - 识别重复问题、高频问题
  - 主动向PM汇报重大信息
  - 更新RAG知识库
  - 按需向其他Agent推送信息
```

### 采集机制

书记员同时运行**被动采集**和**主动采集**两种模式：

#### 数据源类型

```yaml
# 书记员管理的数据采集通道
data_sources:
  # 即时通讯
  - name: 企业微信
    type: IM
    access: API / Webhook
    
  - name: 飞书/钉钉
    type: IM
    access: API / Webhook
    
  # 文档系统
  - name: 内部Wiki
    type: 文档
    access: API / 爬虫
    
  - name: 代码仓库
    type: 代码
    access: Git API
    
  - name: 文档存储
    type: 文件
    access: 文件监控 / API
    
  # 数据库
  - name: 原始素材库
    type: 数据库
    access: SQL / 向量检索
    
  - name: 项目数据库
    type: 数据库
    access: SQL / API
    
  # 外部数据
  - name: 互联网
    type: Web
    access: 爬虫 / API
    
  - name: 行业数据库
    type: 外部
    access: API
```

#### 被动采集

- 信息自动流入：文档更新、消息推送、任务完成通知
- 书记员收到后立即处理：分类、标签、索引

#### 主动采集规则

```yaml
proactive_gathering:
  # 规则1：定时触发
  - trigger: 定时
    schedule: "每天 9:00 / 14:00 / 18:00"
    target: PM
    action: 询问"今天有什么新信息需要采集？"
    
  # 规则2：里程碑触发
  - trigger: 里程碑完成
    event: ["启动会", "规划会", "评审会", "收尾会"]
    target: 会议参与人
    action: 自动请求会议纪要
    
  # 规则3：变化触发
  - trigger: 项目状态变化
    event: ["新需求", "范围变更", "人员变动", "风险升级"]
    target: 相关干系人
    action: 立即询问详情
    
  # 规则4：周期回顾
  - trigger: 周期回顾
    schedule: "每周一"
    target: 全员
    action: 收集"上周有什么值得记录的信息？"
    
  # 规则5：异常检测
  - trigger: 异常模式
    event: ["重复问题", "高频疑问", "规则冲突"]
    target: 相关人员
    action: 主动排查根源
```

#### 采集对象

| 对象 | 采集内容 | 触发时机 |
|------|----------|----------|
| PM | 战略决策、项目方向 | 定时+里程碑 |
| 团队成员 | 工作进展、问题 | 周期+异常 |
| 内务Agent | 流程状态变化 | 事件驱动 |
| 外部系统 | 企微/飞书/邮件 | 异步监听 |
| 项目文档 | 更新内容 | 变化检测 |

#### 两个采集阶段

**阶段一：项目创建时（知识底座打造）**

目标：打造最低可用知识底座（MVP）

```yaml
# 系统性问题清单模板
initial_gathering:
  pm_questions:
    - "项目的核心目标是什么？"
    - "项目的边界在哪里？（包含什么、不包含什么）"
    - "关键干系人有哪些？"
    - "主要风险是什么？"
    - "预期里程碑有哪些？"
    
  team_questions:
    - "业务流程是怎样的？"
    - "有哪些行业术语需要统一？"
    - "有什么内部约定俗成的规则？"
    - "之前项目有什么经验教训？"
    
  external_questions:
    - "行业标准/规范是什么？"
    - "竞争对手是怎么做的？"
    - "有什么外部约束条件？"
```

**阶段二：项目运行中（持续分析）**

目标：分析新信息价值，决定是否深入挖掘

```yaml
value_analysis:
  - step: 价值判断
    questions:
      - "这条信息与项目相关吗？"
      - "属于四层知识体系的哪一层？"
      
  - step: 关系挖掘
    tool_needed: true
    questions:
      - "这个信息与哪些现有概念相关？"
      - "是否触发知识冲突？"
      
  - step: 深度追踪
    decisions:
      - "高价值" → 主动向相关方采集更多
      - "低价值" → 仅索引存档
      - "冲突" → 标记并通知PM/相关Agent
```

> **关系挖掘工具**：书记员需要借助知识图谱或向量检索工具，分析新信息与现有知识的关系。

### 3. 内务Agent

```yaml
role: Housekeeping
name: 内务Agent
alias: 流程引擎

knowledge:
  core:
    - vault/workflows/            # 工作流定义（核心）
    - role/housekeeping/state/    # 流程状态
  reference:
    - vault/code/                 # 了解实现细节
    - vault/decisions/            # 了解决策背景
  base:
    - project.yaml

capabilities:
  - 流程驱动: 触发工作流各节点
  - 定时任务: 定时执行(如考勤、工资)
  - 状态跟踪: 监控流程进度
  - 节点召集: 触发相关人员/Agent

tools:
  - read, glob, grep
  - bash (cron, API)
  - write (状态更新)

autonomy: medium  # 按固定流程执行

behavior:
  - 维护固定流程SOP
  - 按时触发任务
  - 跟踪完成状态
  - 异常时通知PM/调度员
```

### 4. 计划员

```yaml
role: Planner
name: 计划员
alias: 策略引擎

knowledge:
  core:
    - role/planner/rules/          # 阈值规则库
    - vault/plans/                  # 计划库
    - vault/metrics/                # 指标库
  reference:
    - vault/code/                   # 了解实现约束
    - vault/workflows/              # 了解流程限制
  base:
    - project.yaml

capabilities:
  - 变化检测: 监控内外部信息变化
  - 规则引擎: 预设阈值触发条件
  - 计划生成: 基于旧知识+新信息
  - 策略更新: 动态调整方法论

tools:
  - read, glob, grep
  - codesearch, websearch
  - write, edit
  - bash

autonomy: medium  # 超出阈值才主动行动

behavior:
  - 订阅书记员的信息流
  - 维护阈值规则库
  - 超阈值生成新计划/任务
  - 向PM提案新策略
```

### 5. 调度员

```yaml
role: Dispatcher
name: 调度员
alias: 任务路由器

knowledge:
  core:
    - vault/tasks/                 # 任务库
    - role/dispatcher/queue/       # 任务队列状态
  reference:
    - vault/resources/              # 资源清单
    - vault/plans/                  # 了解计划背景
  base:
    - project.yaml

capabilities:
  - 任务分发: 根据类型/负载分配
  - 优先级排序: 紧急/重要分类
  - 资源协调: 避免冲突

autonomy: low  # 执行PM/计划员的指令
```

### 6. 培训员

```yaml
role: Trainer
name: 培训员
alias: 知识传递者

knowledge:
  core:
    - vault/tutorials/             # 教程库
    - vault/faqs/                   # FAQ
    - role/trainer/courses/        # 课程内容
  reference:
    - vault/code/                   # 了解技术细节
    - vault/sops/                   # 了解流程
  base:
    - project.yaml

capabilities:
  - 教程生成: 从经验生成文档
  - 学习追踪: 监控掌握情况
  - 问答系统: 解答常见问题

autonomy: medium
```

---

## 协作流程

```
信息源 (企微/文档/代码)
    ↓
书记员 ← 采集 + 归纳
    ↓ 推送关键信息
PM ← 判断形势
    ↓ 生成策略/任务
计划员 ← 制定计划
    ↓ 任务定义
调度员 ← 分发任务
    ↓ 驱动
内务Agent ← 执行流程
    ↓
培训员 ← 知识沉淀
    ↓
书记员 ← 更新知识库 (闭环)
```

---

## 渐进式实现

| 阶段 | 目标 | 关键角色 |
|------|------|----------|
| v0.1 | 人工为主，Agent辅助 | 书记员(信息汇总) |
| v0.2 | PM开始主导 | PM + 书记员 |
| v0.3 | 流程自动化 | 内务Agent |
| v0.4 | 策略自动生成 | 计划员 |
| v0.5 | 全自动协作 | 全部 |

---

## 下一步

1. **书记员先行** - 最小闭环，信息采集 → RAG → 可查询
2. 定义每个角色的**输入/输出协议**
3. 确定**消息队列**（Agent间如何通信）

你想先从哪个角色开始细化？
