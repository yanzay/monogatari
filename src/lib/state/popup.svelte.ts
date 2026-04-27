import type { Sentence, Token } from '$lib/data/types';

interface PopupState {
  kind: null | 'word' | 'grammar' | 'sentence';
  wordId?: string;
  tok?: Token;
  grammarId?: string;
  sentence?: { story_id: number; sentence_idx: number; data: Sentence };
}

class PopupController {
  current = $state<PopupState>({ kind: null });

  openWord(wordId: string, tok?: Token | null) {
    this.current = { kind: 'word', wordId, tok: tok ?? undefined };
  }

  openGrammar(grammarId: string) {
    this.current = { kind: 'grammar', grammarId };
  }

  openSentence(story_id: number, sentence_idx: number, data: Sentence) {
    this.current = { kind: 'sentence', sentence: { story_id, sentence_idx, data } };
  }

  close() {
    this.current = { kind: null };
  }
}

export const popup = new PopupController();
