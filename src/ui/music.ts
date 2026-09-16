/**
 * §27: the music widget.
 *
 * The track is a commercial recording, so nothing is bundled and nothing is faked. Playback
 * comes from Spotify's official embed, which is the mechanism they publish for exactly this —
 * it handles licensing and pays out, and it plays a preview for anonymous listeners or the
 * full track for someone signed in.
 *
 * The iframe is created the first time the visitor asks for it, not at load: an untouched
 * widget costs no third-party request, no frame, and nothing at startup.
 */
export interface TrackSource {
  play(): Promise<void> | void;
  pause(): void;
  position(): number;
  duration(): number;
}

export interface TrackInfo {
  title: string;
  artist: string;
  /** Spotify track id. Swap this, or replace `mount` entirely, to change the source. */
  spotifyId?: string;
}

export function createMusicWidget(track: TrackInfo, source: TrackSource | null = null) {
  const root = document.getElementById('music') as HTMLElement;
  const toggle = document.getElementById('music-toggle') as HTMLButtonElement;
  const elapsed = document.getElementById('music-elapsed') as HTMLElement;
  const note = document.getElementById('music-note') as HTMLElement;
  const embedHost = document.getElementById('music-embed') as HTMLElement;
  (document.getElementById('music-title') as HTMLElement).textContent = track.title;
  (document.getElementById('music-artist') as HTMLElement).textContent = track.artist;

  let open = false;
  let frame: HTMLIFrameElement | null = null;
  let noteTimer = 0;

  function label(text: string) {
    toggle.querySelector('.sr-only')!.textContent = text;
  }

  function mount() {
    if (frame || !track.spotifyId) return;
    frame = document.createElement('iframe');
    frame.src = `https://open.spotify.com/embed/track/${track.spotifyId}?utm_source=generator&theme=0`;
    frame.width = '100%';
    frame.height = '80';
    frame.loading = 'lazy';
    frame.title = `${track.title} — ${track.artist}`;
    frame.allow = 'encrypted-media; clipboard-write; picture-in-picture';
    frame.setAttribute('frameborder', '0');
    embedHost.append(frame);
  }

  function unmount() {
    // Removing the frame is also how playback stops — there is no other handle on it.
    frame?.remove();
    frame = null;
  }

  function setOpen(next: boolean) {
    open = next;
    root.classList.toggle('is-playing', open);
    toggle.setAttribute('aria-pressed', String(open));
    embedHost.hidden = !open;
    label(open ? 'Close player' : 'Open player');
    if (open) mount();
    else unmount();
  }

  toggle.addEventListener('click', () => {
    if (source) {
      if (open) source.pause();
      else void source.play();
      setOpen(!open);
      return;
    }
    if (!track.spotifyId) {
      window.clearTimeout(noteTimer);
      note.textContent = 'No player connected yet';
      note.hidden = false;
      noteTimer = window.setTimeout(() => (note.hidden = true), 2600);
      return;
    }
    setOpen(!open);
  });

  return {
    /** Fades in once the room is ready, so it is not part of the loading screen. */
    reveal() {
      root.hidden = false;
      requestAnimationFrame(() => root.classList.add('is-visible'));
    },
    /** Only meaningful for a custom source; the embed draws its own progress. */
    update() {
      if (!source || !open) return;
      const d = source.duration();
      elapsed.style.transform = `scaleX(${d > 0 ? Math.min(1, source.position() / d) : 0})`;
    },
  };
}
