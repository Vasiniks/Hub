/**
 * The attribution line the CC BY models require wherever they ship.
 *
 * Read from the props export's `CREDITS.json` (written by `blender/scripts/v2_export_web.py`), so
 * the line always matches the models actually on the site. A short, quiet line in the corner, with
 * each title linking to its source — visible, as the licence asks, without competing with the room.
 */
interface CreditItem {
  title: string;
  author: string;
  licence: string;
  url: string;
}

export async function showCredits(url: string) {
  let items: CreditItem[];
  try {
    const res = await fetch(url);
    if (!res.ok) return;
    items = ((await res.json()) as { items?: CreditItem[] }).items ?? [];
  } catch {
    return;
  }
  if (!items.length) return;

  const footer = document.createElement('footer');
  footer.id = 'credits';
  footer.className = 'credits';
  footer.append('Models: ');
  items.forEach((item, i) => {
    if (i > 0) footer.append(' · ');
    const link = document.createElement('a');
    link.href = item.url;
    link.target = '_blank';
    link.rel = 'noopener';
    link.textContent = item.title;
    footer.append(link, ` by ${item.author} (${item.licence})`);
  });
  document.body.append(footer);
}
