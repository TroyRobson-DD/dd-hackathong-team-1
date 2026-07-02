STATUS_COLORS = {
    "DRAFT":        ("#666666", "#f0f0f0"),
    "SUBMITTED":    ("#1a6fa8", "#dceefa"),
    "UNDER_REVIEW": ("#8a6000", "#fff3cd"),
    "APPROVED":     ("#1a7a3f", "#d4edda"),
    "REJECTED":     ("#a81a1a", "#fde8e8"),
    "PAID":         ("#155724", "#c3e6cb"),
    "CANCELLED":    ("#555555", "#e2e2e2"),
}


def status_badge(status: str) -> str:
    color, bg = STATUS_COLORS.get(status, ("#333", "#eee"))
    return (
        f'<span style="background:{bg};color:{color};padding:2px 10px;'
        f'border-radius:12px;font-size:0.82em;font-weight:600;">{status}</span>'
    )


def fmt_currency(amount, currency: str = "AUD") -> str:
    if amount is None:
        return "—"
    symbol = "$" if currency in ("AUD", "USD", "NZD") else currency + " "
    return f"{symbol}{amount:,.2f}"


def fmt_date(d) -> str:
    if d is None:
        return "—"
    try:
        return d.strftime("%-d %b %Y")
    except Exception:
        return str(d)


def role_chip(role: str) -> str:
    colors = {
        "ADMIN":   ("#fff", "#6f42c1"),
        "FINANCE": ("#fff", "#0d6efd"),
        "MANAGER": ("#fff", "#198754"),
        "STAFF":   ("#fff", "#6c757d"),
    }
    fg, bg = colors.get(role, ("#fff", "#333"))
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 9px;'
        f'border-radius:10px;font-size:0.78em;font-weight:700;">{role}</span>'
    )
