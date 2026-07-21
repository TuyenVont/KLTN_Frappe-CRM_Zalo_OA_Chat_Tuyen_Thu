from __future__ import annotations

from crm.www.crm import get_context as get_crm_context


def get_context(context):
    """
    Lấy boot context từ CRM gốc rồi gộp vào context
    của trang crm_reports_shell.
    """

    context.no_cache = 1

    # CRM hiện tại định nghĩa get_context() không có tham số.
    core_context = get_crm_context()

    if isinstance(core_context, dict):
        context.update(core_context)

    elif core_context is not None:
        # Dự phòng nếu CRM trả về object thay vì dict.
        for key, value in vars(core_context).items():
            context[key] = value

    return context