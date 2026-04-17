import { COMPONENT_MAP, createComponent } from "./component-library.js";
import {
  deepClone,
  duplicateNode,
  findNode,
  findParentInfo,
  insertAfter,
  insertInside,
  moveNode,
  moveNodeByOffset,
  removeNode,
  sanitizeModel
} from "./tree-utils.js";

export const STORAGE_KEY = "dictionary-ui-editor-draft-v1";

function applyPatchToNode(root, id, patch) {
  if (root.id === id) {
    const next = deepClone(root);
    next.props = { ...(next.props || {}), ...(patch.props || {}) };
    next.style = { ...(next.style || {}), ...(patch.style || {}) };
    next.states = {
      hover: { ...(next.states?.hover || {}), ...(patch.states?.hover || {}) },
      focus: { ...(next.states?.focus || {}), ...(patch.states?.focus || {}) }
    };
    return next;
  }
  const next = deepClone(root);
  next.children = (root.children || []).map((child) => applyPatchToNode(child, id, patch));
  return next;
}

export function createEditorStore(initialModel) {
  let state = {
    model: sanitizeModel(initialModel),
    selectedId: initialModel.root?.children?.[0]?.id || initialModel.root?.id || "page-root",
    mode: "edit",
    viewport: "desktop",
    theme: "light",
    status: "Hazır",
    lastSavedAt: null
  };

  const listeners = new Set();
  const history = {
    past: [],
    future: []
  };

  function emit() {
    for (const listener of listeners) {
      listener(getState());
    }
  }

  function getState() {
    return {
      ...state,
      canUndo: history.past.length > 0,
      canRedo: history.future.length > 0
    };
  }

  function commit(updater, options = {}) {
    const { historyable = true, status = state.status } = options;
    const previous = deepClone(state);
    const next = updater(deepClone(state));
    if (!next) {
      return;
    }
    next.status = status;
    state = next;
    if (historyable) {
      history.past.push(previous);
      history.future = [];
      if (history.past.length > 80) {
        history.past.shift();
      }
    }
    emit();
  }

  return {
    getState,
    getSelectedNode() {
      return findNode(state.model.root, state.selectedId);
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    actions: {
      select(id) {
        state.selectedId = id;
        emit();
      },
      setMode(mode) {
        state.mode = mode;
        state.status = mode === "edit" ? "Düzen modu aktif." : "Kullanım önizlemesi aktif.";
        emit();
      },
      setViewport(viewport) {
        state.viewport = viewport;
        state.status = `Önizleme genişliği: ${viewport}`;
        emit();
      },
      setTheme(theme) {
        state.theme = theme;
        emit();
      },
      addComponent(type, targetId, placement = "inside") {
        const definition = COMPONENT_MAP[type];
        if (!definition) {
          return;
        }
        const node = createComponent(type);
        commit((draft) => {
          draft.model.meta.updatedAt = new Date().toISOString();
          draft.model.root =
            placement === "inside"
              ? insertInside(draft.model.root, targetId, node)
              : insertAfter(draft.model.root, targetId, node);
          draft.selectedId = node.id;
          return draft;
        }, { status: `${definition.label} eklendi.` });
      },
      updateNodeState(nodeId, patch) {
        if (!nodeId) {
          return;
        }
        commit((draft) => {
          draft.model.root = applyPatchToNode(draft.model.root, nodeId, patch);
          draft.model.meta.updatedAt = new Date().toISOString();
          return draft;
        }, { status: "Özellikler güncellendi." });
      },
      replaceModel(model, status = "Düzen yüklendi.") {
        commit((draft) => {
          draft.model = sanitizeModel(model);
          draft.selectedId = draft.model.root.children?.[0]?.id || draft.model.root.id;
          return draft;
        }, { status });
      },
      applyTemplate(templateFactory) {
        this.replaceModel(templateFactory(), "Şablon uygulandı.");
      },
      deleteSelected() {
        if (!state.selectedId || state.selectedId === state.model.root.id) {
          return;
        }
        commit((draft) => {
          const info = findParentInfo(draft.model.root, draft.selectedId);
          const removal = removeNode(draft.model.root, draft.selectedId);
          draft.model.root = removal.root;
          draft.selectedId = info?.parent?.id || draft.model.root.id;
          return draft;
        }, { status: "Bileşen silindi." });
      },
      duplicateSelected() {
        if (!state.selectedId || state.selectedId === state.model.root.id) {
          return;
        }
        commit((draft) => {
          draft.model.root = duplicateNode(draft.model.root, draft.selectedId);
          return draft;
        }, { status: "Bileşen kopyalandı." });
      },
      moveSelected(offset) {
        if (!state.selectedId || state.selectedId === state.model.root.id) {
          return;
        }
        commit((draft) => {
          draft.model.root = moveNodeByOffset(draft.model.root, draft.selectedId, offset);
          return draft;
        }, { status: "Bileşen sırası güncellendi." });
      },
      moveExistingNode(sourceId, targetId, placement = "inside") {
        if (!sourceId || !targetId || sourceId === targetId) {
          return;
        }
        commit((draft) => {
          draft.model.root = moveNode(draft.model.root, sourceId, targetId, placement);
          draft.selectedId = sourceId;
          return draft;
        }, { status: "Bileşen taşındı." });
      },
      saveDraft() {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state.model));
        state.lastSavedAt = new Date().toISOString();
        state.status = "Taslak kaydedildi.";
        emit();
      },
      undo() {
        if (!history.past.length) {
          return;
        }
        history.future.unshift(deepClone(state));
        state = history.past.pop();
        state.status = "Geri alındı.";
        emit();
      },
      redo() {
        if (!history.future.length) {
          return;
        }
        history.past.push(deepClone(state));
        state = history.future.shift();
        state.status = "İleri alındı.";
        emit();
      }
    }
  };
}

export function loadStoredDraft() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}
