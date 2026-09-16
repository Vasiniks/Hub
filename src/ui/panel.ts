import type { ProjectDef } from '../data/projects';

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

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

  return {
    get isOpen() {
      return panel.classList.contains('is-open');
    },
    fill(project: ProjectDef) {
      kind.textContent = project.kindLabel;
      title.textContent = project.title;
      summary.textContent = project.summary;
      sections.replaceChildren(
        ...project.sections.map((s) => {
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
  projects: ProjectDef[],
  handlers: { onFocus: (id: string) => void; onBlur: () => void; onActivate: (id: string) => void },
) {
  const nav = $('object-nav');
  for (const p of projects) {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = p.placeholder ? `${p.title} (${p.kindLabel.toLowerCase()})` : p.title;
    b.addEventListener('focus', () => handlers.onFocus(p.id));
    b.addEventListener('blur', handlers.onBlur);
    b.addEventListener('click', () => handlers.onActivate(p.id));
    nav.append(b);
  }
}
