import { COMPONENT_MAP } from "./component-library.js";
import { toKebabCase, walkTree } from "./tree-utils.js";

function applyStyles(element, style = {}) {
  const styleMap = { ...style };
  const textColor = styleMap.textColor;
  delete styleMap.textColor;
  for (const [key, value] of Object.entries(styleMap)) {
    if (value === "" || value === null || value === undefined) {
      continue;
    }
    element.style[key] = value;
  }
  if (textColor) {
    element.style.color = textColor;
  }
}

function cssBlock(selector, styles = {}) {
  const rules = Object.entries(styles)
    .filter(([, value]) => value !== "" && value !== null && value !== undefined)
    .map(([key, value]) => `${toKebabCase(key === "textColor" ? "color" : key)}:${value};`)
    .join("");
  return rules ? `${selector}{${rules}}` : "";
}

function renderTextNode(tagName, node) {
  const element = document.createElement(tagName);
  element.textContent = node.props.text || "";
  return element;
}

function renderSearchBox(node) {
  const wrapper = document.createElement("div");
  wrapper.style.display = "flex";
  wrapper.style.gap = node.style.gap || "10px";
  wrapper.style.alignItems = "center";

  const input = document.createElement("input");
  input.type = "search";
  input.placeholder = node.props.placeholder || "";
  input.value = node.props.text || "";
  input.disabled = true;
  input.style.flex = "1";
  input.style.padding = "12px 14px";
  input.style.borderRadius = "12px";
  input.style.border = "1px solid rgba(18,34,28,0.12)";

  const button = document.createElement("button");
  button.type = "button";
  button.textContent = node.props.buttonText || "Ara";
  button.style.padding = "12px 16px";
  button.style.borderRadius = "12px";
  button.style.border = "0";
  button.style.background = "#1c6a58";
  button.style.color = "#fff";
  wrapper.append(input, button);
  return wrapper;
}

function renderList(node) {
  const wrapper = document.createElement("div");
  if (node.props.title) {
    const title = document.createElement("strong");
    title.textContent = node.props.title;
    title.style.display = "block";
    title.style.marginBottom = "12px";
    wrapper.append(title);
  }
  const list = document.createElement("ul");
  list.style.margin = "0";
  list.style.paddingLeft = "18px";
  const items = String(node.props.items || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  for (const item of items) {
    const li = document.createElement("li");
    li.textContent = item;
    li.style.marginBottom = "8px";
    list.append(li);
  }
  wrapper.append(list);
  return wrapper;
}

function renderChipRow(node) {
  const wrapper = document.createElement("div");
  wrapper.style.display = "flex";
  wrapper.style.flexWrap = "wrap";
  wrapper.style.gap = node.style.gap || "8px";
  const items = String(node.props.items || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  for (const item of items) {
    const chip = document.createElement("span");
    chip.textContent = item;
    chip.style.padding = "7px 12px";
    chip.style.borderRadius = "999px";
    chip.style.background = "rgba(28, 106, 88, 0.12)";
    chip.style.color = "#1c6a58";
    chip.style.fontWeight = "600";
    chip.style.fontSize = "0.82rem";
    wrapper.append(chip);
  }
  return wrapper;
}

function renderWordCardHeader(node) {
  const wrapper = document.createElement("div");
  wrapper.style.display = "flex";
  wrapper.style.flexDirection = "column";
  wrapper.style.gap = "8px";

  const word = document.createElement("h2");
  word.textContent = node.props.word || "";
  word.style.margin = "0";
  word.style.fontSize = "2rem";

  const translation = document.createElement("p");
  translation.textContent = node.props.translation || "";
  translation.style.margin = "0";
  translation.style.fontSize = "1.4rem";
  translation.style.color = "#1c6a58";
  translation.style.fontWeight = "700";

  const meta = document.createElement("span");
  meta.textContent = node.props.meta || "";
  meta.style.color = "#6a7a72";
  meta.style.fontSize = "0.92rem";

  wrapper.append(word, translation, meta);
  return wrapper;
}

function renderMeaningBlock(node) {
  const wrapper = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = node.props.title || "Kısa bilgi";
  title.style.display = "block";
  title.style.marginBottom = "10px";
  const body = document.createElement("p");
  body.textContent = node.props.text || "";
  body.style.margin = "0";
  wrapper.append(title, body);
  return wrapper;
}

function renderExampleBlock(node) {
  const wrapper = document.createElement("div");
  wrapper.style.display = "grid";
  wrapper.style.gap = "10px";
  const german = document.createElement("p");
  german.innerHTML = `<strong>DE</strong> ${node.props.german || ""}`;
  german.style.margin = "0";
  const turkish = document.createElement("p");
  turkish.innerHTML = `<strong>TR</strong> ${node.props.turkish || ""}`;
  turkish.style.margin = "0";
  wrapper.append(german, turkish);
  return wrapper;
}

function renderNodeContent(node) {
  switch (node.type) {
    case "section":
    case "card":
    case "sidebar": {
      if (!node.props.title && !node.props.text) {
        return null;
      }
      const wrapper = document.createElement("div");
      if (node.props.title) {
        const title = document.createElement("strong");
        title.textContent = node.props.title;
        title.style.display = "block";
        title.style.marginBottom = node.props.text ? "8px" : "0";
        wrapper.append(title);
      }
      if (node.props.text) {
        const body = document.createElement("p");
        body.textContent = node.props.text;
        body.style.margin = "0";
        wrapper.append(body);
      }
      return wrapper;
    }
    case "heading":
      return renderTextNode(`h${node.props.level || 2}`, node);
    case "text":
      return renderTextNode("p", node);
    case "button":
    case "favorite-button": {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `${node.props.icon ? `${node.props.icon} ` : ""}${node.props.text || ""}`;
      return button;
    }
    case "input": {
      const input = document.createElement("input");
      input.type = "text";
      input.placeholder = node.props.placeholder || "";
      input.value = node.props.text || "";
      input.disabled = true;
      return input;
    }
    case "search-box":
      return renderSearchBox(node);
    case "list":
      return renderList(node);
    case "chip-row":
      return renderChipRow(node);
    case "word-card":
      return renderWordCardHeader(node);
    case "meaning-block":
      return renderMeaningBlock(node);
    case "example-block":
      return renderExampleBlock(node);
    case "modal": {
      const card = document.createElement("div");
      card.style.maxWidth = "420px";
      card.style.margin = "36px auto";
      card.style.padding = "22px";
      card.style.borderRadius = "18px";
      card.style.background = "#ffffff";
      card.innerHTML = `<strong style="display:block;margin-bottom:10px;">${node.props.title || ""}</strong><p style="margin:0;">${node.props.text || ""}</p>`;
      return card;
    }
    case "navbar": {
      const wrapper = document.createElement("div");
      wrapper.style.display = "flex";
      wrapper.style.justifyContent = "space-between";
      wrapper.style.alignItems = "center";
      const title = document.createElement("strong");
      title.textContent = node.props.title || "";
      const items = document.createElement("span");
      items.textContent = String(node.props.items || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean)
        .join("   ");
      wrapper.append(title, items);
      return wrapper;
    }
    default:
      return null;
  }
}

function decorateNode(element, node, context) {
  const definition = COMPONENT_MAP[node.type] || { container: true };
  element.classList.add("canvas-node");
  element.dataset.nodeId = node.id;
  element.dataset.renderId = node.id;
  element.dataset.nodeType = node.type;
  element.dataset.container = definition.container ? "true" : "false";
  applyStyles(element, node.style || {});
  element.style.textAlign = node.props.align === "center" ? "center" : node.props.align === "right" ? "right" : "";
  if (node.props.visible === false) {
    element.style.display = "none";
  }
  if (context.mode === "edit") {
    element.classList.add("is-editable");
    element.draggable = node.id !== context.rootId;
    element.addEventListener("click", (event) => {
      event.stopPropagation();
      context.onSelect(node.id);
    });
    element.addEventListener("dragstart", (event) => {
      event.dataTransfer.setData("application/x-layout-node", node.id);
      event.dataTransfer.effectAllowed = "move";
    });
    element.addEventListener("dragover", (event) => {
      event.preventDefault();
      element.dataset.dropState = "active";
    });
    element.addEventListener("dragleave", () => {
      element.dataset.dropState = "";
    });
    element.addEventListener("drop", (event) => {
      event.preventDefault();
      element.dataset.dropState = "";
      const componentType = event.dataTransfer.getData("application/x-layout-component");
      const movingId = event.dataTransfer.getData("application/x-layout-node");
      const placement = definition.container ? "inside" : "after";
      if (componentType) {
        context.onPaletteDrop(componentType, node.id, placement);
        return;
      }
      if (movingId) {
        context.onMoveDrop(movingId, node.id, placement);
      }
    });
    if (context.selectedId === node.id) {
      element.classList.add("is-selected");
    }
    if (node.id !== context.rootId) {
      const toolbar = document.createElement("div");
      toolbar.className = "canvas-node-toolbar";
      toolbar.textContent = definition.label || node.type;
      element.append(toolbar);
    }
  }
}

function renderComponent(node, context) {
  const definition = COMPONENT_MAP[node.type] || { container: true };
  const tag = node.type === "word-card" ? "article" : node.type === "navbar" ? "nav" : node.type === "sidebar" ? "aside" : "section";
  const element = document.createElement(tag);
  decorateNode(element, node, context);

  const content = renderNodeContent(node);
  if (content) {
    element.append(content);
  }

  if (definition.container) {
    for (const child of node.children || []) {
      element.append(renderComponent(child, context));
    }
    if (context.mode === "edit" && (!node.children || node.children.length === 0)) {
      const hint = document.createElement("div");
      hint.className = "drop-hint";
      hint.textContent = "Bileşen bırakmak için uygun alan";
      element.append(hint);
    }
  }

  return element;
}

function generateInteractionCss(root) {
  const parts = [];
  walkTree(root, (node) => {
    parts.push(cssBlock(`[data-render-id="${node.id}"]:hover`, node.states?.hover || {}));
    parts.push(cssBlock(`[data-render-id="${node.id}"]:focus-within`, node.states?.focus || {}));
  });
  return parts.filter(Boolean).join("\n");
}

export function renderLayout(model, mountNode, options) {
  mountNode.replaceChildren();

  if (!model.root.children?.length) {
    const empty = document.createElement("div");
    empty.className = "canvas-empty-state";
    empty.innerHTML = "<div><strong>Canvas boş</strong>Soldan bileşen sürükleyerek düzen oluşturmaya başla.</div>";
    mountNode.append(empty);
    return;
  }

  const styleTag = document.createElement("style");
  styleTag.textContent = generateInteractionCss(model.root);
  mountNode.append(styleTag);

  mountNode.append(
    renderComponent(model.root, {
      ...options,
      rootId: model.root.id
    })
  );
}
