/**
 * Dummy books for the shelf-browsing mechanic. Content comes later (§35): these exist to give
 * the selection interaction real objects with real variation in size, colour and proportion.
 */
export interface BookDef {
  id: string;
  title: string;
  author: string;
  /** Spine thickness and height in metres — the variation is the point. */
  thickness: number;
  height: number;
  /** Cover field colour and the accent used for the rule and mark. */
  color: string;
  accent: string;
  /** Slight lean in the row, in radians. A few books are not perfectly upright. */
  lean?: number;
  note: string;
}

const note = 'Placeholder. Notes on this book go here later.';

export const books: BookDef[] = [
  { id: 'b1', title: 'Placeholder One', author: 'Author', thickness: 0.032, height: 0.235, color: '#2f3a44', accent: '#c7d2dc', note },
  { id: 'b2', title: 'Placeholder Two', author: 'Author', thickness: 0.021, height: 0.208, color: '#6a3f34', accent: '#e8c9a8', lean: 0.03, note },
  { id: 'b3', title: 'Placeholder Three', author: 'Author', thickness: 0.044, height: 0.248, color: '#24443a', accent: '#b9d9c6', note },
  { id: 'b4', title: 'Placeholder Four', author: 'Author', thickness: 0.018, height: 0.196, color: '#4a4550', accent: '#d5cbdc', note },
  { id: 'b5', title: 'Placeholder Five', author: 'Author', thickness: 0.038, height: 0.226, color: '#1f3350', accent: '#aec4e0', note },
  { id: 'b6', title: 'Placeholder Six', author: 'Author', thickness: 0.026, height: 0.242, color: '#5c4a24', accent: '#e4d3a4', lean: -0.04, note },
  { id: 'b7', title: 'Placeholder Seven', author: 'Author', thickness: 0.03, height: 0.202, color: '#3c3f44', accent: '#cdd3d9', note },
  { id: 'b8', title: 'Placeholder Eight', author: 'Author', thickness: 0.023, height: 0.23, color: '#5a2b32', accent: '#e6bcbe', note },
  { id: 'b9', title: 'Placeholder Nine', author: 'Author', thickness: 0.041, height: 0.214, color: '#27404a', accent: '#b6d2da', note },
  { id: 'b10', title: 'Placeholder Ten', author: 'Author', thickness: 0.019, height: 0.244, color: '#453a2e', accent: '#dcc9b0', lean: 0.05, note },
  { id: 'b11', title: 'Placeholder Eleven', author: 'Author', thickness: 0.035, height: 0.219, color: '#2c3660', accent: '#bcc3e8', note },
  { id: 'b12', title: 'Placeholder Twelve', author: 'Author', thickness: 0.027, height: 0.2, color: '#374039', accent: '#c6d2c4', note },
];
