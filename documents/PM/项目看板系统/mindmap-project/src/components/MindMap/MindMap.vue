<template>
  <div class="mindmap-container">
    <div id="jsmind-container"></div>
    <ContextMenu 
      v-if="menuVisible" 
      :x="menuX" 
      :y="menuY" 
      :node="selectedNode"
      @close="closeMenu"
      @add="handleAddChild"
      @edit="handleEdit"
      @delete="handleDelete"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useMindMapStore } from '../../stores/mindmap'
import jsMind from 'jsmind'
import jsMindDraggable from 'jsmind/es6/jsmind.draggable-node.js'
import 'jsmind/style/jsmind.css'
import ContextMenu from './ContextMenu.vue'

const emit = defineEmits(['node-click'])

const store = useMindMapStore()
const jm = ref(null)
const menuVisible = ref(false)
const menuX = ref(0)
const menuY = ref(0)
const selectedNode = ref(null)

console.log('[MindMap] jsMindDraggable 插件:', jsMindDraggable)

function loadMindMap() {
  console.log('[MindMap] 初始化脑图...')
  console.log('[MindMap] 拖拽插件:', jsMindDraggable)
  
  const options = {
    container: 'jsmind-container',
    theme: 'primary',
    editable: true,
    mode: 'full',
    support_html: true,
    view: {
      hspace: 100,
      vspace: 30,
      line_width: 2,
      line_color: '#555'
    },
    layout: {
      hspace: 100,
      vspace: 30
    }
  }
  
  jm.value = new jsMind(options)
  console.log('[MindMap] jsMind 实例创建完成')
  
  // 启用拖拽插件
  if (jsMindDraggable) {
    console.log('[MindMap] 启用拖拽插件...')
    const draggable = new jsMindDraggable(jm.value, {
      handle: 'jmnode',
      enable: true
    })
    console.log('[MindMap] 拖拽插件已启用', draggable)
  }
  
  render()
  
  // 监听所有事件
  jm.value.add_event_listener((type, data) => {
    console.log('[MindMap] 事件:', type, data)
  })
  
  jm.value.add_event_listener('click', handleNodeClick)
  jm.value.add_event_listener('contextmenu', handleContextMenu)
  jm.value.add_event_listener('dragstart', handleDragStart)
  jm.value.add_event_listener('dragend', handleDragEnd)
  
  console.log('[MindMap] 事件监听器绑定完成')
}

function render() {
  if (!jm.value || !store.mindData) return
  
  const mind = {
    meta: {
      name: 'project-mindmap',
      author: 'PM System',
      version: '1.0'
    },
    format: 'node_tree',
    data: transformToJsMind(store.mindData)
  }
  
  jm.value.show(mind)
}

function transformToJsMind(node) {
  const result = {
    id: node.id,
    text: node.title,
    expanded: true
  }
  
  if (node.children && node.children.length > 0) {
    result.children = node.children.map(child => transformToJsMind(child))
  }
  
  return result
}

function handleNodeClick(node) {
  const found = store.findNode(store.mindData, node.id)
  if (found) {
    store.selectNode(found)
    emit('node-click', found)
  }
}

function handleContextMenu(node, e) {
  e.preventDefault()
  
  const found = store.findNode(store.mindData, node.id)
  if (found) {
    selectedNode.value = found
    menuX.value = e.clientX
    menuY.value = e.clientY
    menuVisible.value = true
  }
}

let draggedNodeId = null

function handleDragStart(node) {
  console.log('[MindMap] dragstart:', node)
  draggedNodeId = node?.id
}

function handleDragEnd(node, targetNode) {
  console.log('[MindMap] dragend:', { node: node?.id, target: targetNode?.id })
  if (targetNode && draggedNodeId && draggedNodeId !== targetNode.id) {
    console.log('[MindMap] 移动节点:', draggedNodeId, '->', targetNode.id)
    store.moveNode(draggedNodeId, targetNode.id)
    render()
  }
  draggedNodeId = null
}

function closeMenu() {
  menuVisible.value = false
}

function handleAddChild() {
  const newNode = {
    id: 'node-' + Date.now(),
    title: '新节点',
    node_type: 'task',
    children: []
  }
  
  if (selectedNode.value) {
    store.addNode(selectedNode.value.id, newNode)
    render()
  }
  closeMenu()
}

function handleEdit() {
  const newTitle = prompt('请输入节点标题:', selectedNode.value?.title)
  if (newTitle && selectedNode.value) {
    store.updateNode(selectedNode.value.id, { title: newTitle })
    render()
  }
  closeMenu()
}

function handleDelete() {
  if (selectedNode.value && confirm('确定删除该节点及其所有子节点？')) {
    store.deleteNode(selectedNode.value.id)
    render()
  }
  closeMenu()
}

onMounted(() => {
  loadMindMap()
})

watch(() => store.mindData, () => {
  if (jm.value) {
    render()
  }
}, { deep: true })
</script>

<style scoped>
.mindmap-container {
  width: 100%;
  height: 100%;
  position: relative;
}

#jsmind-container {
  width: 100%;
  height: 100%;
}

:deep(.jsmind-inner) {
  background: #1e1e1e;
}

:deep(.jsmind-node) {
  background: #2d2d30;
  border: 1px solid #3e3e42;
  border-radius: 4px;
  padding: 8px 16px;
  color: #d4d4d4;
}

:deep(.jsmind-node.selected) {
  border-color: #4ec9b0;
  background: #094771;
}
</style>
