
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

/**
 * What a panel shows: one small kicker, a title, a summary and labelled rows. Projects, books and
 * v2 props all reduce to this, so there is one kind of surface in the room (§34).
 */
export interface PanelContent {
  kind: string;
  title: string;
  summary: string;
  sections: { label: string; body: string }[];
}

export function createPanel(onClose: () => void) {
  const panel = $('panel');
  const kind = $('panel-kind');
  const title = $('panel-title');
  const summary = $('panel-summary');
  const sections = $('panel-sections');
  const close = $<HTMLButtonElement>('panel-close');
  let returnFocus: HTMLElement | null = null;
  let hideTimer = 0;

  close.addEventListener('click', onClose);
  // Clicks inside the panel never count as "outside".
  panel.addEventListener('pointerdown', (e) => e.stopPropagation());

  function write(kindText: string, titleText: string, summaryText: string, rows: { label: string; body: string }[]) {
    kind.textContent = kindText;
    title.textContent = titleText;
    summary.textContent = summaryText;
    sections.replaceChildren(
      ...rows.map((s) => {
        const row = document.createElement('div');
        const dt = document.createElement('dt');
        const dd = document.createElement('dd');
        dt.textContent = s.label;
        dd.textContent = s.body;
        row.append(dt, dd);
        return row;
      }),
    );
    panel.scrollTop = 0;
  }

  return {
    get isOpen() {
      return panel.classList.contains('is-open');
    },
    /** Fill the panel with an object's content (kind, title, summary, sections). */
    fillContent(content: PanelContent) {
      write(content.kind, content.title, content.summary, content.sections);
    },
    open() {
      window.clearTimeout(hideTimer);
      returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      panel.hidden = false;
      requestAnimationFrame(() => {
        panel.classList.add('is-open');
        title.focus({ preventScroll: true });
      });
    },
    close() {
      panel.classList.remove('is-open');
      hideTimer = window.setTimeout(() => (panel.hidden = true), 260);
      if (returnFocus && returnFocus !== document.body && returnFocus.closest('#object-nav')) {
        returnFocus.focus({ preventScroll: true });
      } else if (panel.contains(document.activeElement)) {
        (document.activeElement as HTMLElement).blur();
      }
      returnFocus = null;
    },
  };
}

export function createHint() {
  const el = $('hint');
  let timer = 0;
  return {
    show(text: string, autoHideMs = 0) {
      window.clearTimeout(timer);
      el.textContent = text;
      el.classList.add('is-visible');
      if (autoHideMs) timer = window.setTimeout(() => el.classList.remove('is-visible'), autoHideMs);
    },
    hide() {
      window.clearTimeout(timer);
      el.classList.remove('is-visible');
    },
  };
}

export function createObjectNav(
  items: { id: string; label: string }[],
  handlers: { onFocus: (id: string) => void; onBlur: () => void; onActivate: (id: string) => void },
) {
  const nav = $('object-nav');
  const add = (item: { id: string; label: string }) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = item.label;
    b.dataset.id = item.id;
    b.addEventListener('focus', () => handlers.onFocus(item.id));
    b.addEventListener('blur', handlers.onBlur);
    b.addEventListener('click', () => handlers.onActivate(item.id));
    nav.append(b);
  };
  items.forEach(add);
  return {
    /** Objects that arrive after start-up (v2 props register as their GLBs load). */
    add,
  };
}
