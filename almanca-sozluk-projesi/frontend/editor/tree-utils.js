export function createId(prefix = "node") {
  return `${prefix}-${Math.random().toString(36).slice(2, 8)}-${Date.now().toString(36)}`;
}

export function deepClone(value) {
  return JSON.parse(JSON.stringify(value));
}

export function toKebabCase(value) {
  return String(value || "").replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`);
}

export function assignFreshIds(node) {
  const cloned = deepClone(node);

  function walk(current) {
    current.id = createId(current.type || "node");
    current.children = Array.isArray(current.children) ? current.children : [];
    for (const child of current.children) {
      walk(child);
    }
  }

  walk(cloned);
  return cloned;
}

export function findNode(root, id) {
  if (!root || !id) {
    return null;
  }
  if (root.id === id) {
    return root;
  }
  for (const child of root.children || []) {
    const found = findNode(child, id);
    if (found) {
      return found;
    }
  }
  return null;
}

export function findParentInfo(root, id, parent = null) {
  if (!root || !id) {
    return null;
  }
  if (root.id === id) {
    return { node: root, parent };
  }
  for (const child of root.children || []) {
    const found = findParentInfo(child, id, root);
    if (found) {
      return found;
    }
  }
  return null;
}

export function walkTree(node, visitor, depth = 0, parent = null) {
  if (!node) {
    return;
  }
  visitor(node, depth, parent);
  for (const child of node.children || []) {
    walkTree(child, visitor, depth + 1, node);
  }
}

export function removeNode(root, id) {
  if (!root || root.id === id) {
    return { root, removed: null };
  }

  let removed = null;

  function walk(current) {
    const next = deepClone(current);
    next.children = [];
    for (const child of current.children || []) {
      if (child.id === id) {
        removed = deepClone(child);
        continue;
      }
      next.children.push(walk(child));
    }
    return next;
  }

  return { root: walk(root), removed };
}

function updateNode(root, id, updater) {
  if (!root) {
    return root;
  }
  if (root.id === id) {
    return updater(deepClone(root));
  }
  const nextRoot = deepClone(root);
  nextRoot.children = (root.children || []).map((child) => updateNode(child, id, updater));
  return nextRoot;
}

export function insertInside(root, parentId, node, index = null) {
  return updateNode(root, parentId, (parentNode) => {
    parentNode.children = Array.isArray(parentNode.children) ? parentNode.children : [];
    if (index === null || index < 0 || index > parentNode.children.length) {
      parentNode.children.push(node);
    } else {
      parentNode.children.splice(index, 0, node);
    }
    return parentNode;
  });
}

export function insertAfter(root, targetId, node) {
  const info = findParentInfo(root, targetId);
  if (!info?.parent) {
    return root;
  }
  return updateNode(root, info.parent.id, (parentNode) => {
    const index = (parentNode.children || []).findIndex((child) => child.id === targetId);
    if (index === -1) {
      parentNode.children.push(node);
    } else {
      parentNode.children.splice(index + 1, 0, node);
    }
    return parentNode;
  });
}

export function isAncestor(root, ancestorId, childId) {
  const ancestor = findNode(root, ancestorId);
  if (!ancestor) {
    return false;
  }
  return Boolean(findNode(ancestor, childId));
}

export function moveNode(root, sourceId, targetId, placement = "inside") {
  if (!root || !sourceId || !targetId || sourceId === root.id || sourceId === targetId) {
    return root;
  }
  if (placement === "inside" && isAncestor(root, sourceId, targetId)) {
    return root;
  }

  const removal = removeNode(root, sourceId);
  if (!removal.removed) {
    return root;
  }

  if (placement === "inside") {
    return insertInside(removal.root, targetId, removal.removed);
  }
  return insertAfter(removal.root, targetId, removal.removed);
}

export function duplicateNode(root, id) {
  const node = findNode(root, id);
  if (!node) {
    return root;
  }
  return insertAfter(root, id, assignFreshIds(node));
}

export function moveNodeByOffset(root, id, offset) {
  const info = findParentInfo(root, id);
  if (!info?.parent) {
    return root;
  }
  return updateNode(root, info.parent.id, (parentNode) => {
    const children = [...(parentNode.children || [])];
    const index = children.findIndex((item) => item.id === id);
    if (index === -1) {
      return parentNode;
    }
    const nextIndex = index + offset;
    if (nextIndex < 0 || nextIndex >= children.length) {
      return parentNode;
    }
    const [item] = children.splice(index, 1);
    children.splice(nextIndex, 0, item);
    parentNode.children = children;
    return parentNode;
  });
}

export function sanitizeModel(model) {
  if (!model || typeof model !== "object" || !model.root) {
    throw new Error("Geçerli bir düzen JSON'u bulunamadı.");
  }
  const next = deepClone(model);
  next.meta = next.meta || {};
  next.meta.version = next.meta.version || 1;
  next.root.id = next.root.id || createId("page");
  next.root.type = next.root.type || "page";
  next.root.children = Array.isArray(next.root.children) ? next.root.children : [];
  walkTree(next.root, (node) => {
    node.id = node.id || createId(node.type || "node");
    node.props = node.props || {};
    node.style = node.style || {};
    node.states = node.states || { hover: {}, focus: {} };
    node.children = Array.isArray(node.children) ? node.children : [];
  });
  return next;
}
