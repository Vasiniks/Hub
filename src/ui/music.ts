/**
 * §31: the shell of a music widget.
 *
 * Deliberately just a shell. The intended track is a commercial recording, so nothing is
 * bundled here and nothing is faked: with no source connected the transport stays inert and
 * says so, rather than animating a progress bar over silence. When a real player is wired up
 * later — an embed or a licensed preview — it implements `TrackSource` and the widget starts
 * reflecting it without any other change.
 */
export interface TrackSource {
  play(): Promise<void> | void;
  pause(): void;
  /** Seconds. */
  position(): number;
  duration(): number;
}

export interface TrackInfo {
  title: string;
  artist: string;
}

export function createMusicWidget(track: TrackInfo, source: TrackSource | null = null) {
  const root = document.getElementById('music') as HTMLElement;
  const toggle = document.getElementById('music-toggle') as HTMLButtonElement;
  const elapsed = document.getElementById('music-elapsed') as HTMLElement;
  const note = document.getElementById('music-note') as HTMLElement;
  (document.getElementById('music-title') as HTMLElement).textContent = track.title;
  (document.getElementById('music-artist') as HTMLElement).textContent = track.artist;

  let playing = false;
  let noteTimer = 0;

  function setPlaying(next: boolean) {
    playing = next;
    root.classList.toggle('is-playing', playing);
    toggle.setAttribute('aria-pressed', String(playing));
    toggle.querySelector('.sr-only')!.textContent = playing ? 'Pause' : 'Play';
  }

  toggle.addEventListener('click', () => {
    if (!source) {
      window.clearTimeout(noteTimer);
      note.textContent = 'No player connected yet';
      note.hidden = false;
      noteTimer = window.setTimeout(() => (note.hidden = true), 2600);
      return;
    }
    if (playing) source.pause();
    else void source.play();
    setPlaying(!playing);
  });

  return {
    /** Fades in once the room is ready, so it is not part of the loading screen. */
    reveal() {
      root.hidden = false;
      requestAnimationFrame(() => root.classList.add('is-visible'));
    },
    /** Called at a low rate from the loop; with no source there is nothing to move. */
    update() {
      if (!source || !playing) return;
      const d = source.duration();
      elapsed.style.transform = `scaleX(${d > 0 ? Math.min(1, source.position() / d) : 0})`;
    },
  };
}
