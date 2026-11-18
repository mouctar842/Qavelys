import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { configure } from '@testing-library/dom';
import { afterEach, vi } from 'vitest';
// jsdom ne fournit pas encore les méthodes natives de <dialog>.
HTMLDialogElement.prototype.showModal = function () { this.open = true; };
HTMLDialogElement.prototype.close = function () { this.open = false; };
configure({ asyncUtilTimeout: 5000 });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
