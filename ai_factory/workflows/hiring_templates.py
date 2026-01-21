from __future__ import annotations

"""招聘相关工作流模板构造函数。

目前包含：
- 面试流程：hiring_interview_v1
- 入职流程：hiring_onboarding_v1

后续可根据需要继续扩展或细化节点。
"""

from .workflow_config import WorkflowNode, WorkflowTemplate


def build_hiring_interview_template_v1() -> WorkflowTemplate:
    """构造招聘-面试流程 v1 的 WorkflowTemplate。"""

    nodes = [
        WorkflowNode(
            id="phone_screen",
            name="电话面试",
            kind="human_form",
            swimlane="电话面试",
            role="HR",
            ui={
                "form_schema_id": "interview_phone_v1",
                "participants": ["candidate", "hr"],
                "cc_list": [],
            },
            constraints={"sla_seconds": 3600},
        ),
        WorkflowNode(
            id="schedule_meeting",
            name="约面试时间地点",
            kind="human_form",
            swimlane="约面试",
            role="HR",
            ui={
                "form_schema_id": "interview_schedule_v1",
                "participants": ["candidate", "hr"],
            },
        ),
        WorkflowNode(
            id="onsite_interview",
            name="现场问答+记录印象",
            kind="human_form",
            swimlane="现场面谈",
            role="HR",
            ui={
                "form_schema_id": "interview_onsite_v1",
                "fixed_question_set_id": "interview_questions_v1",
                "participants": ["candidate", "hr"],
            },
        ),
        WorkflowNode(
            id="offer_discussion",
            name="待遇与工作要求沟通",
            kind="human_form",
            swimlane="待遇沟通",
            role="HR",
            ui={
                "form_schema_id": "interview_offer_v1",
                "participants": ["candidate", "hr"],
            },
        ),
        WorkflowNode(
            id="site_trial",
            name="现场看工",
            kind="human_form",
            swimlane="看工",
            role="班组长",
            ui={
                "form_schema_id": "interview_site_trial_v1",
                "participants": ["candidate", "team_leader"],
                "cc_list": ["hr"],
            },
        ),
        WorkflowNode(
            id="beike_interview",
            name="贝壳面试",
            kind="human_approve",
            swimlane="贝壳面试",
            role="贝壳负责人",
            ui={
                "form_schema_id": "interview_beike_v1",
                "participants": ["candidate", "beike_manager"],
                "cc_list": ["hr", "team_leader"],
                "show_on_board": True,
            },
        ),
    ]

    edges = [
        ("phone_screen", "schedule_meeting"),
        ("schedule_meeting", "onsite_interview"),
        ("onsite_interview", "offer_discussion"),
        ("offer_discussion", "site_trial"),
        ("site_trial", "beike_interview"),
    ]

    template = WorkflowTemplate(
        template_id="hiring_interview_v1",
        name="招聘-面试流程 v1",
        description=(
            "电话面试 → 约面试 → 现场问答 → 待遇沟通 → 看工 → 贝壳面试，"
            "成功后进入入职流程"
        ),
        version=1,
        category="hiring",
        nodes=nodes,
        edges=edges,
        start_node="phone_screen",
        end_nodes=["beike_interview"],
        meta={
            "on_success_next_template_id": "hiring_onboarding_v1",
            "planning_binding": {
                "allowed_planning_types": ["工作流"],
                "default_lane_dimension": "workflow",
            },
        },
    )

    return template


def build_hiring_onboarding_template_v1() -> WorkflowTemplate:
    """构造招聘-入职流程 v1 的 WorkflowTemplate。"""

    nodes = [
        WorkflowNode(
            id="collect_contacts",
            name="收集领导与班组长微信",
            kind="human_form",
            swimlane="联系方式确认",
            role="HR",
            ui={
                "form_schema_id": "onboard_contacts_v1",
                "participants": ["hr"],
                "cc_list": ["team_leader"],
            },
        ),
        WorkflowNode(
            id="collect_personal_info",
            name="收集个人信息与证件",
            kind="human_form",
            swimlane="证件信息",
            role="HR",
            ui={
                "form_schema_id": "onboard_personal_v1",
                "participants": ["hr", "candidate"],
                "cc_list": [],
            },
        ),
        WorkflowNode(
            id="record_start_dates",
            name="记录上工与起薪日期",
            kind="system_task",
            swimlane="系统登记",
            role="HR",
            handler="record_start_and_salary_dates",
            ui={
                "show_on_board": True,
            },
        ),
    ]

    edges = [
        ("collect_contacts", "collect_personal_info"),
        ("collect_personal_info", "record_start_dates"),
    ]

    template = WorkflowTemplate(
        template_id="hiring_onboarding_v1",
        name="招聘-入职流程 v1",
        description="收集联系方式 → 收集证件与个人信息 → 记录上工与起薪日期",
        version=1,
        category="hiring",
        nodes=nodes,
        edges=edges,
        start_node="collect_contacts",
        end_nodes=["record_start_dates"],
        meta={
            "planning_binding": {
                "allowed_planning_types": ["工作流"],
                "default_lane_dimension": "workflow",
            },
        },
    )

    return template
