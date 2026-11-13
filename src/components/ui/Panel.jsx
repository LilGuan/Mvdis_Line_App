export default function Panel({ title, aside, children, className = "" }) {
  return (
    <section className={`panel ${className}`}>
      {(title || aside) && (
        <div className="panel-hd">
          <span className="panel-title">{title}</span>
          {aside}
        </div>
      )}
      <div className="panel-body">{children}</div>
    </section>
  );
}
