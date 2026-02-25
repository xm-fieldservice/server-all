import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const STORAGE_KEY = 'mindmap_data'
const API_BASE = 'http://localhost:8000/api'

// 默认脑图数据
const defaultMind = {
  id: 'root',
  title: '项目看板',
  node_type: 'root',
  children: [
    {
      id: 'strategy-1',
      title: '战略目标',
      node_type: 'strategy',
      children: [
        { id: 'goal-1', title: '目标1', node_type: 'goal', children: [] }
      ]
    },
    {
      id: 'project-1',
      title: '项目A',
      node_type: 'project',
      children: [
        { id: 'task-1', title: '任务1', node_type: 'task', children: [] }
      ]
    }
  ]
}

export const useMindMapStore = defineStore('mindmap', () => {
  // 状态
  const mindData = ref(null)
  const selectedNode = ref(null)
  const isEditing = ref(false)
  const autoSync = ref(false)
  const lastSyncTime = ref(null)

  // 初始化：从 localStorage 加载或使用默认数据
  function init() {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      try {
        mindData.value = JSON.parse(stored)
      } catch (e) {
        mindData.value = JSON.parse(JSON.stringify(defaultMind))
      }
    } else {
      mindData.value = JSON.parse(JSON.stringify(defaultMind))
    }
  }

  // 保存到 localStorage
  function save() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(mindData.value))
    if (autoSync.value) {
      syncToBackend()
    }
  }

  // 同步到后端 API
  async function syncToBackend() {
    try {
      const response = await fetch(`${API_BASE}/mindmap/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(mindData.value)
      })
      if (response.ok) {
        lastSyncTime.value = new Date().toISOString()
        console.log('已同步到后端:', lastSyncTime.value)
      }
    } catch (e) {
      console.warn('后端同步失败:', e.message)
    }
  }

  // 手动触发同步
  async function manualSync() {
    await syncToBackend()
  }

  // 启用/禁用自动同步
  function setAutoSync(enabled) {
    autoSync.value = enabled
    if (enabled) {
      syncToBackend()
    }
  }

  // 查找节点
  function findNode(node, id) {
    if (node.id === id) return node
    if (node.children) {
      for (const child of node.children) {
        const found = findNode(child, id)
        if (found) return found
      }
    }
    return null
  }

  // 查找父节点
  function findParent(node, id, parent = null) {
    if (node.id === id) return parent
    if (node.children) {
      for (const child of node.children) {
        const found = findParent(child, id, node)
        if (found) return found
      }
    }
    return null
  }

  // 添加节点
  function addNode(parentId, newNode) {
    const parent = findNode(mindData.value, parentId)
    if (parent) {
      if (!parent.children) parent.children = []
      parent.children.push(newNode)
      save()
    }
  }

  // 更新节点
  function updateNode(id, updates) {
    const node = findNode(mindData.value, id)
    if (node) {
      Object.assign(node, updates)
      save()
    }
  }

  // 删除节点
  function deleteNode(id) {
    if (id === 'root') return // 不能删除根节点
    
    const parent = findParent(mindData.value, id)
    if (parent && parent.children) {
      parent.children = parent.children.filter(child => child.id !== id)
      save()
    }
  }

  // 移动节点（拖拽）
  function moveNode(nodeId, targetId) {
    const node = findNode(mindData.value, nodeId)
    const targetParent = findNode(mindData.value, targetId)
    
    if (node && targetParent && nodeId !== targetId) {
      // 从原父节点移除
      const oldParent = findParent(mindData.value, nodeId)
      if (oldParent && oldParent.children) {
        oldParent.children = oldParent.children.filter(child => child.id !== nodeId)
      }
      
      // 添加到新父节点
      if (!targetParent.children) targetParent.children = []
      targetParent.children.push(node)
      
      save()
    }
  }

  // 选中节点
  function selectNode(node) {
    selectedNode.value = node
  }

  // 初始化
  init()

  return {
    mindData,
    selectedNode,
    isEditing,
    autoSync,
    lastSyncTime,
    init,
    save,
    syncToBackend,
    manualSync,
    setAutoSync,
    findNode,
    findParent,
    addNode,
    updateNode,
    deleteNode,
    moveNode,
    selectNode
  }
})
