import type { Token } from '$lib/data/types';

interface PopupState {
  kind: null | 'word' | 'grammar';
  wordId?: string;
  tok?: Token;
  grammarId?: string;
}

class PopupController {
  current = $state<PopupState>({ kind: null });

  openWord(wordId: string, tok?: Token | null) {
    this.current = { kind: 'word', wordId, tok: tok ?? undefined };
  }

  openGrammar(grammarId: string) {
    this.current = { kind: 'grammar', grammarId };
  }

  close() {
    this.current = { kind: null };
  }
}

export const popup = new PopupController();
