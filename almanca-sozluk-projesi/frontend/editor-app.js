import { COMPONENT_DEFINITIONS, COMPONENT_MAP } from "./editor/component-library.js";
import { createEditorStore, loadStoredDraft, STORAGE_KEY } from "./editor/store.js";
import { createInitialModel, TEMPLATES } from "./editor/templates.js";
import { findNode, sanitizeModel } from "./editor/tree-utils.js";
import { renderLayout } from "./editor/renderer.js";

const componentPaletteNode = document.querySelector("#component-palette");
const templateListNode = document.querySelector("#template-list");
const previewRootNode = document.querySelector("#preview-root");
const previewFrameNode = document.querySelector("#preview-frame");
const inspectorRootNode = document.querySelector("#inspector-root");
const workspaceTitleNode = document.querySelector("#workspace-title");
const workspaceStatusNode = document.querySelector("#workspace-status");
const workspaceModeBadgeNode = document.querySelector("#workspace-mode-badge");
const saveButton = document.querySelector("#save-button");
const undoButton = document.querySelector("#undo-button");
const redoButton = document.querySelector("#redo-button");
const previewButton = document.querySelector("#preview-button");
const editModeButton = document.querySelector("#edit-mode-button");
const useModeButton = document.querySelector("#use-mode-button");
const exportButton = document.querySelector("#export-button");
const importButton = document.querySelector("#import-button");
const importInput = document.querySelector("#import-input");

const storedDraft = loadStoredDraft();
const store = createEditorStore(storedDraft || createInitialModel());

let autosaveTimer = null;

function setStatus(text) {
  workspaceStatusNode.textContent = text;
}

function groupedPaletteItems() {
  const groups = new Map();
  for (const item of COMPONENT_DEFINITIONS) {
    if (!groups.has(item.group)) {
      groups.set(item.group, []);
    }
    groups.get(item.group).push(item);
  }
  return groups;
}

function createField(labelText, control) {
  const field = document.createElement("div");
  field.className = "field";
  const label = document.createElement("label");
  label.textContent = labelText;
  field.append(label, control);
  return field;
}

function createInput(type, value, onInput) {
  const input = document.createElement("input");
  input.type = type;
  input.value = value ?? "";
  input.addEventListener("input", () => onInput(input.value));
  return input;
}

function createTextArea(value, onInput) {
  const textarea = document.createElement("textarea");
  textarea.value = value ?? "";
  textarea.addEventListener("input", () => onInput(textarea.value));
  return textarea;
}

function createSelect(value, options, onChange) {
  const select = document.createElement("select");
  for (const optionValue of options) {
    const option = document.createElement("option");
    option.value = optionValue;
    option.textContent = optionValue;
    option.selected = value === optionValue;
    select.append(option);
  }
  select.addEventListener("change", () => onChange(select.value));
  return select;
}

function updateSegmentedButtons(selector, activeValue, attributeName) {
  document.querySelectorAll(selector).forEach((button) => {
    button.classList.toggle("is-active", button.dataset[attributeName] === activeValue);
  });
}

function renderPalette() {
  componentPaletteNode.replaceChildren();
  for (const [groupName, items] of groupedPaletteItems()) {
    const title = document.createElement("p");
    title.className = "palette-group-title";
    title.textContent = groupName;
    componentPaletteNode.append(title);
    for (const item of items) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "palette-item";
      button.draggable = true;
      button.innerHTML = `<span><strong>${item.label}</strong><span>${item.description}</span></span><span class="component-badge">${item.icon}</span>`;
      button.addEventListener("dragstart", (event) => {
        event.dataTransfer.setData("application/x-layout-component", item.type);
        event.dataTransfer.effectAllowed = "copy";
      });
      button.addEventListener("click", () => {
        const { selectedId, model } = store.getState();
        const target = findNode(model.root, selectedId) || model.root;
        const placement = (COMPONENT_MAP[target.type]?.container ?? target.id === model.root.id) ? "inside" : "after";
        store.actions.addComponent(item.type, target.id, placement);
      });
      componentPaletteNode.append(button);
    }
  }
}

function renderTemplates() {
  templateListNode.replaceChildren();
  for (const template of TEMPLATES) {
    const card = document.createElement("article");
    card.className = "template-card";
    card.innerHTML = `<h3>${template.name}</h3><p>${template.description}</p>`;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Şablonu Yükle";
    button.addEventListener("click", () => {
      if (window.confirm(`${template.name} düzeni mevcut canvas'ın yerine yüklensin mi?`)) {
        store.actions.applyTemplate(template.build);
      }
    });
    card.append(button);
    templateListNode.append(card);
  }
}

function attachModelDropZone() {
  previewRootNode.addEventListener("dragover", (event) => {
    event.preventDefault();
  });
  previewRootNode.addEventListener("drop", (event) => {
    event.preventDefault();
    const componentType = event.dataTransfer.getData("application/x-layout-component");
    const movingId = event.dataTransfer.getData("application/x-layout-node");
    if (componentType) {
      store.actions.addComponent(componentType, store.getState().model.root.id, "inside");
    } else if (movingId) {
      store.actions.moveExistingNode(movingId, store.getState().model.root.id, "inside");
    }
  });
}

function renderInspector() {
  const { model, selectedId } = store.getState();
  const node = findNode(model.root, selectedId);
  inspectorRootNode.replaceChildren();

  if (!node) {
    const empty = document.createElement("div");
    empty.className = "inspector-empty";
    empty.innerHTML = "<strong>Bileşen seçilmedi</strong><p>Canvas üzerinde bir bileşene tıkla ya da soldan yeni bileşen ekle.</p>";
    inspectorRootNode.append(empty);
    return;
  }

  const info = document.createElement("div");
  info.className = "inspector-group";
  info.innerHTML = `<h3>${COMPONENT_MAP[node.type]?.label || node.type}</h3><div class="field-grid"></div>`;
  const infoGrid = info.querySelector(".field-grid");
  const idInput = createInput("text", node.id, () => {});
  idInput.disabled = true;
  const typeInput = createInput("text", COMPONENT_MAP[node.type]?.label || node.type, () => {});
  typeInput.disabled = true;
  infoGrid.append(createField("ID", idInput), createField("Tip", typeInput));
  inspectorRootNode.append(info);

  const contentGroup = document.createElement("div");
  contentGroup.className = "inspector-group";
  contentGroup.innerHTML = "<h3>İçerik</h3>";
  const contentGrid = document.createElement("div");
  contentGrid.className = "field-grid";
  contentGroup.append(contentGrid);

  const contentFields = [
    ["Metin", "text"],
    ["Başlık", "title"],
    ["Kelime", "word"],
    ["Çeviri", "translation"],
    ["Meta", "meta"],
    ["Placeholder", "placeholder"],
    ["Buton Metni", "buttonText"],
    ["İkon", "icon"],
    ["Liste / Öğeler", "items"],
    ["DE Cümle", "german"],
    ["TR Cümle", "turkish"]
  ];

  for (const [label, key] of contentFields) {
    if (!(key in (node.props || {}))) {
      continue;
    }
    const control =
      key === "text"
        ? createTextArea(node.props[key], (value) => store.actions.updateNodeState(node.id, { props: { [key]: value } }))
        : createInput("text", node.props[key], (value) => store.actions.updateNodeState(node.id, { props: { [key]: value } }));
    contentGrid.append(createField(label, control));
  }

  contentGrid.append(
    createField(
      "Görünürlük",
      createSelect(String(node.props.visible !== false), ["true", "false"], (value) =>
        store.actions.updateNodeState(node.id, { props: { visible: value === "true" } })
      )
    ),
    createField(
      "Hizalama",
      createSelect(node.props.align || "left", ["left", "center", "right", "space-between", "stretch"], (value) =>
        store.actions.updateNodeState(node.id, { props: { align: value } })
      )
    )
  );

  if ("level" in (node.props || {})) {
    contentGrid.append(
      createField(
        "Başlık Seviyesi",
        createSelect(String(node.props.level || "2"), ["1", "2", "3", "4"], (value) =>
          store.actions.updateNodeState(node.id, { props: { level: value } })
        )
      )
    );
  }

  inspectorRootNode.append(contentGroup);

  const styleGroup = document.createElement("div");
  styleGroup.className = "inspector-group";
  styleGroup.innerHTML = "<h3>Stil</h3>";
  const styleGrid = document.createElement("div");
  styleGrid.className = "field-grid";
  styleGroup.append(styleGrid);

  const styleFields = [
    ["Font Size", "fontSize"],
    ["Font Weight", "fontWeight"],
    ["Text Color", "textColor"],
    ["Background", "backgroundColor"],
    ["Padding", "padding"],
    ["Margin", "margin"],
    ["Width", "width"],
    ["Height", "height"],
    ["Border Width", "borderWidth"],
    ["Border Style", "borderStyle"],
    ["Border Color", "borderColor"],
    ["Border Radius", "borderRadius"],
    ["Gap", "gap"],
    ["Box Shadow", "boxShadow"]
  ];

  for (const [label, key] of styleFields) {
    const control =
      key === "borderStyle"
        ? createSelect(node.style?.[key] || "solid", ["solid", "dashed", "none"], (value) =>
            store.actions.updateNodeState(node.id, { style: { [key]: value } })
          )
        : createInput("text", node.style?.[key] || "", (value) =>
            store.actions.updateNodeState(node.id, { style: { [key]: value } })
          );
    styleGrid.append(createField(label, control));
  }

  inspectorRootNode.append(styleGroup);

  const statesGroup = document.createElement("div");
  statesGroup.className = "inspector-group";
  statesGroup.innerHTML = "<h3>Hover / Focus</h3>";
  const statesGrid = document.createElement("div");
  statesGrid.className = "field-grid";
  statesGroup.append(statesGrid);

  const interactionFields = [
    ["Hover Background", "hover", "backgroundColor"],
    ["Hover Text", "hover", "textColor"],
    ["Hover Border", "hover", "borderColor"],
    ["Focus Border", "focus", "borderColor"],
    ["Focus Shadow", "focus", "boxShadow"]
  ];

  for (const [label, stateKey, styleKey] of interactionFields) {
    const control = createInput("text", node.states?.[stateKey]?.[styleKey] || "", (value) =>
      store.actions.updateNodeState(node.id, { states: { [stateKey]: { [styleKey]: value } } })
    );
    statesGrid.append(createField(label, control));
  }

  inspectorRootNode.append(statesGroup);

  const actionsGroup = document.createElement("div");
  actionsGroup.className = "inspector-group";
  actionsGroup.innerHTML = "<h3>Aksiyonlar</h3>";
  const actions = document.createElement("div");
  actions.className = "inspector-actions";

  const duplicate = document.createElement("button");
  duplicate.className = "inspector-action";
  duplicate.type = "button";
  duplicate.textContent = "Kopyala";
  duplicate.addEventListener("click", () => store.actions.duplicateSelected());

  const up = document.createElement("button");
  up.className = "inspector-action";
  up.type = "button";
  up.textContent = "Yukarı Taşı";
  up.addEventListener("click", () => store.actions.moveSelected(-1));

  const down = document.createElement("button");
  down.className = "inspector-action";
  down.type = "button";
  down.textContent = "Aşağı Taşı";
  down.addEventListener("click", () => store.actions.moveSelected(1));

  const remove = document.createElement("button");
  remove.className = "inspector-action";
  remove.type = "button";
  remove.textContent = "Sil";
  remove.addEventListener("click", () => {
    if (node.id !== model.root.id && window.confirm("Seçili bileşen silinsin mi?")) {
      store.actions.deleteSelected();
    }
  });

  actions.append(duplicate, up, down, remove);
  actionsGroup.append(actions);
  inspectorRootNode.append(actionsGroup);
}

function renderPreview() {
  const current = store.getState();
  workspaceTitleNode.textContent = current.model.meta?.name || "Düzen";
  workspaceModeBadgeNode.textContent = current.mode === "edit" ? "Düzen modu" : "Kullanım modu";
  setStatus(current.status);

  previewFrameNode.className = `preview-frame preview-frame-${current.viewport}`;
  renderLayout(current.model, previewRootNode, {
    mode: current.mode,
    selectedId: current.selectedId,
    onSelect: (id) => store.actions.select(id),
    onPaletteDrop: (type, targetId, placement) => store.actions.addComponent(type, targetId, placement),
    onMoveDrop: (sourceId, targetId, placement) => store.actions.moveExistingNode(sourceId, targetId, placement)
  });
}

function updateTopbar() {
  const current = store.getState();
  undoButton.disabled = !current.canUndo;
  redoButton.disabled = !current.canRedo;
  updateSegmentedButtons("[data-viewport]", current.viewport, "viewport");
  updateSegmentedButtons("[data-theme-toggle]", current.theme, "themeToggle");
  editModeButton.classList.toggle("is-active", current.mode === "edit");
  useModeButton.classList.toggle("is-active", current.mode === "use");
  document.body.dataset.theme = current.theme;
}

function autoSave() {
  window.clearTimeout(autosaveTimer);
  autosaveTimer = window.setTimeout(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store.getState().model));
  }, 280);
}

function exportJson() {
  const payload = JSON.stringify(store.getState().model, null, 2);
  const blob = new Blob([payload], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "dictionary-layout.json";
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}

function importJson(file) {
  if (!file) {
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const model = sanitizeModel(JSON.parse(String(reader.result || "")));
      store.actions.replaceModel(model, "JSON içe aktarıldı.");
    } catch (error) {
      window.alert(error.message || "JSON yüklenemedi.");
    }
  };
  reader.readAsText(file, "utf-8");
}

function bindTopbarActions() {
  saveButton.addEventListener("click", () => store.actions.saveDraft());
  undoButton.addEventListener("click", () => store.actions.undo());
  redoButton.addEventListener("click", () => store.actions.redo());
  previewButton.addEventListener("click", () => store.actions.setMode("use"));
  editModeButton.addEventListener("click", () => store.actions.setMode("edit"));
  useModeButton.addEventListener("click", () => store.actions.setMode("use"));
  exportButton.addEventListener("click", exportJson);
  importButton.addEventListener("click", () => importInput.click());
  importInput.addEventListener("change", () => importJson(importInput.files?.[0]));
  document.querySelectorAll("[data-viewport]").forEach((button) => {
    button.addEventListener("click", () => store.actions.setViewport(button.dataset.viewport));
  });
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.addEventListener("click", () => store.actions.setTheme(button.dataset.themeToggle));
  });
}

function renderApp() {
  renderPreview();
  renderInspector();
  updateTopbar();
  autoSave();
}

renderPalette();
renderTemplates();
attachModelDropZone();
bindTopbarActions();
store.subscribe(renderApp);
renderApp();
