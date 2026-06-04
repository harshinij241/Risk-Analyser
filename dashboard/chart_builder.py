import json
import plotly.graph_objects as go
import plotly.express as px
from knowledge_risk.models import RiskScore
from llm.models import LLMSummary


def _risk_color(score: float) -> str:
    """Map risk score to color."""
    if score >= 75:
        return "#E63946"   # red
    if score >= 40:
        return "#F4A261"   # amber
    return "#2A9D8F"       # green


def build_treemap(scores: list[RiskScore],
                  summaries: dict[str, LLMSummary]) -> str:
    """
    Treemap where:
    - Each rectangle = one file
    - Size = complexity score
    - Color = risk score (green → amber → red)
    - Hover = full breakdown
    """
    if not scores:
        return "{}"

    ids, labels, parents     = [], [], []
    values, colors, hovers   = [], [], []

    # Build directory hierarchy for treemap nesting
    dirs = set()
    for s in scores:
        parts = s.file_path.split("/")
        for i in range(1, len(parts)):
            dirs.add("/".join(parts[:i]))

    # Add directory nodes
    for d in sorted(dirs):
        ids.append(d)
        labels.append(d.split("/")[-1])
        parent = "/".join(d.split("/")[:-1])
        parents.append(parent)
        values.append(0)
        colors.append(0)
        hovers.append("")

    # Add file nodes
    for s in scores:
        summary = summaries.get(s.file_path)
        what    = (summary.what_it_does[:80] + "..."
                   if summary and len(summary.what_it_does) > 80
                   else (summary.what_it_does if summary else ""))

        parent = "/".join(s.file_path.split("/")[:-1])

        ids.append(s.file_path)
        labels.append(s.file_path.split("/")[-1])
        parents.append(parent)
        values.append(max(0.01, s.complexity))
        colors.append(s.score)
        hovers.append(
            f"<b>{s.file_path}</b><br>"
            f"Risk Score: {s.score:.1f}<br>"
            f"Confidence: {s.confidence}<br>"
            f"Living Knowledge: {s.living_knowledge:.0%}<br>"
            f"Top Author: "
            f"{s.top_authors[0][0] if s.top_authors else 'unknown'}"
            f"<br><br>{what}"
        )

    fig = go.Figure(go.Treemap(
        ids           = ids,
        labels        = labels,
        parents       = parents,
        values        = values,
        customdata    = hovers,
        hovertemplate = "%{customdata}<extra></extra>",
        marker        = dict(
            colors    = colors,
            colorscale= [
                [0.0,  "#2A9D8F"],
                [0.4,  "#F4A261"],
                [1.0,  "#E63946"]
            ],
            cmin      = 0,
            cmax      = 100,
            showscale = True,
            colorbar  = dict(
                title = "Risk Score",
                tickvals = [0, 40, 75, 100],
                ticktext = ["Low", "Medium", "High", "Critical"]
            )
        ),
        textinfo      = "label",
        pathbar       = dict(visible=True)
    ))

    fig.update_layout(
        title     = "Codebase Knowledge Risk Map",
        margin    = dict(t=40, l=0, r=0, b=0),
        height    = 500,
        paper_bgcolor = "rgba(0,0,0,0)",
        plot_bgcolor  = "rgba(0,0,0,0)",
        font      = dict(family="Inter, sans-serif")
    )

    return fig.to_json()


def build_network_graph(scores: list[RiskScore]) -> str:
    """
    Network graph where:
    - Developer nodes (circles) connect to file nodes (squares)
    - Edge thickness = contribution share
    - File node color = risk score
    - Shows knowledge silos visually
    """
    if not scores:
        return "{}"

    # Collect all unique authors
    all_authors = set()
    for s in scores:
        for author, _ in s.top_authors:
            all_authors.add(author)

    authors = list(all_authors)

    # Layout: authors on left, files on right
    author_y = {
        a: i * (1.0 / max(len(authors) - 1, 1))
        for i, a in enumerate(authors)
    }

    # Build edge traces
    edge_traces = []
    for s in scores:
        file_idx = scores.index(s)
        file_y   = file_idx * (1.0 / max(len(scores) - 1, 1))

        for author, share in s.top_authors:
            ay = author_y.get(author, 0.5)
            edge_traces.append(go.Scatter(
                x         = [0, 1, None],
                y         = [ay, file_y, None],
                mode      = "lines",
                line      = dict(
                    width = max(1, share * 8),
                    color = _risk_color(s.score)
                ),
                hoverinfo = "skip",
                showlegend= False
            ))

    # Author nodes
    author_trace = go.Scatter(
        x         = [0] * len(authors),
        y         = [author_y[a] for a in authors],
        mode      = "markers+text",
        text      = authors,
        textposition = "middle left",
        marker    = dict(
            size  = 16,
            color = "#4361EE",
            symbol= "circle",
            line  = dict(width=2, color="white")
        ),
        hovertemplate = "<b>%{text}</b><extra></extra>",
        name      = "Developers"
    )

    # File nodes
    file_names  = [s.file_path.split("/")[-1] for s in scores]
    file_colors = [s.score for s in scores]
    file_y_vals = [
        i * (1.0 / max(len(scores) - 1, 1))
        for i in range(len(scores))
    ]

    file_trace = go.Scatter(
        x            = [1] * len(scores),
        y            = file_y_vals,
        mode         = "markers+text",
        text         = file_names,
        textposition = "middle right",
        customdata   = [s.score for s in scores],
        hovertemplate= (
            "<b>%{text}</b><br>"
            "Risk: %{customdata:.1f}<extra></extra>"
        ),
        marker       = dict(
            size     = 14,
            color    = file_colors,
            colorscale = [
                [0.0, "#2A9D8F"],
                [0.4, "#F4A261"],
                [1.0, "#E63946"]
            ],
            cmin     = 0,
            cmax     = 100,
            symbol   = "square",
            line     = dict(width=2, color="white")
        ),
        name         = "Files"
    )

    fig = go.Figure(
        data   = edge_traces + [author_trace, file_trace],
        layout = go.Layout(
            title       = "Developer–File Knowledge Network",
            height      = 600,
            showlegend  = True,
            hovermode   = "closest",
            margin      = dict(t=40, l=120, r=120, b=20),
            xaxis       = dict(
                showgrid=False, zeroline=False,
                showticklabels=False
            ),
            yaxis       = dict(
                showgrid=False, zeroline=False,
                showticklabels=False
            ),
            paper_bgcolor = "rgba(0,0,0,0)",
            plot_bgcolor  = "rgba(0,0,0,0)",
            font          = dict(family="Inter, sans-serif")
        )
    )

    return fig.to_json()