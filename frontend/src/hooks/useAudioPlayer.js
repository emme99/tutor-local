import { useRef, useCallback } from "react";

/**
 * Riproduzione sequenziale di clip audio (base64) restituiti dal backend.
 * Gestisce reply + explanations_audio_segments + audio_segments.
 */
export function useAudioPlayer() {
  const player = useRef(null);

  const stop = useCallback(() => {
    player.current?.pause();
    player.current = null;
  }, []);

  const play = useCallback((payload, onEnd) => {
    const clips = [
      payload?.audio_b64 && {
        audio_b64: payload.audio_b64,
        audio_mime: payload.audio_mime,
      },
      ...(payload?.explanations_audio_segments || []),
      ...(payload?.audio_segments || []),
    ].filter(Boolean);

    if (!clips.length) {
      onEnd?.();
      return;
    }

    player.current?.pause();
    let index = 0;
    const playNext = () => {
      if (index >= clips.length) {
        onEnd?.();
        return;
      }
      const clip = clips[index++];
      const a = new Audio(`data:${clip.audio_mime};base64,${clip.audio_b64}`);
      player.current = a;
      a.onended = playNext;
      a.play().catch(playNext);
    };
    playNext();
  }, []);

  return { play, stop, player };
}
