import { pages } from "../../data/options";

export default function Sidebar({ activePage, onChange }) {
  const groups = [...new Set(pages.map((page) => page.group))];

  return (
    <aside className="sidebar">
      {groups.map((group) => (
        <div key={group}>
          <div className="nav-section">{group}</div>
          {pages.filter((page) => page.group === group).map((page) => (
            <button
              className={`nav-btn ${activePage === page.id ? "active" : ""}`}
              key={page.id}
              onClick={() => onChange(page.id)}
            >
              <span className="nav-icon">{page.icon}</span>
              {page.label}
            </button>
          ))}
        </div>
      ))}
    </aside>
  );
}
