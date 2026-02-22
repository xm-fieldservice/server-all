<template>
  <div class="devlab">
    <header class="header">
      <div class="scene-switches">
        <button 
          v-for="scene in scenes" 
          :key="scene.value"
          :class="['scene-btn', { active: currentScene === scene.value }]"
          @click="currentScene = scene.value"
        >
          {{ scene.label }}
        </button>
      </div>
      <div class="actions">
        <label class="sync-toggle">
          <input type="checkbox" v-model="autoSyncEnabled" @change="handleAutoSyncChange">
          <span>自动同步</span>
        </label>
        <button class="btn" @click="handleSave">保存到本地</button>
        <button class="btn success" @click="handleSync">同步到后端</button>
        <button class="btn" @click="handleExport">导出</button>
      </div>
    </header>
    
    <div class="main-content">
      <div class="mindmap-panel">
        <MindMap ref="mindmapRef" @node-click="handleNodeClick" />
      </div>
      
      <div class="side-panel">
        <div class="panel-section">
          <h3>问答</h3>
          <ChatPanel />
        </div>
        <div class="panel-section">
          <h3>笔记</h3>
          <NotesPanel />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import MindMap from '../components/MindMap/MindMap.vue'
import ChatPanel from '../components/Chat/ChatPanel.vue'
import NotesPanel from '../components/Notes/NotesPanel.vue'
import { useMindMapStore } from '../stores/mindmap'

const store = useMindMapStore()
const mindmapRef = ref(null)
const currentScene = ref('all')
const autoSyncEnabled = ref(store.autoSync)

const scenes = [
  { label: '大循环', value: 'big' },
  { label: '小循环', value: 'small' },
  { label: '全部', value: 'all' }
]

function handleNodeClick(node) {
  console.log('选中节点:', node)
}

function handleSave() {
  store.save()
  alert('已保存到浏览器本地存储')
}

function handleAutoSyncChange() {
  store.setAutoSync(autoSyncEnabled.value)
}

async function handleSync() {
  await store.manualSync()
  if (store.lastSyncTime) {
    alert('已同步到后端: ' + new Date(store.lastSyncTime).toLocaleTimeString())
  } else {
    alert('后端同步失败（可能后端未启动）')
  }
}

function handleExport() {
  const data = JSON.stringify(store.mindData, null, 2)
  const blob = new Blob([data], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'mindmap.json'
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.devlab {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #1e1e1e;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  background: #252526;
  border-bottom: 1px solid #3e3e42;
}

.scene-switches {
  display: flex;
  gap: 8px;
}

.scene-btn {
  padding: 6px 16px;
  background: transparent;
  border: 1px solid #3e3e42;
  border-radius: 4px;
  color: #a0a0a0;
  cursor: pointer;
  transition: all 0.2s;
}

.scene-btn:hover {
  border-color: #4ec9b0;
  color: #d4d4d4;
}

.scene-btn.active {
  background: #4ec9b0;
  border-color: #4ec9b0;
  color: #1e1e1e;
}

.actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.sync-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #a0a0a0;
  font-size: 12px;
  cursor: pointer;
}

.sync-toggle input {
  cursor: pointer;
}

.btn {
  padding: 6px 16px;
  background: #0e639c;
  border: none;
  border-radius: 4px;
  color: white;
  cursor: pointer;
  font-size: 12px;
}

.btn:hover {
  background: #1177bb;
}

.btn.success {
  background: #27ae60;
}

.btn.success:hover {
  background: #2ecc71;
}

.main-content {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.mindmap-panel {
  flex: 1;
  overflow: hidden;
}

.side-panel {
  width: 360px;
  background: #252526;
  border-left: 1px solid #3e3e42;
  display: flex;
  flex-direction: column;
}

.panel-section {
  padding: 16px;
  border-bottom: 1px solid #3e3e42;
}

.panel-section h3 {
  font-size: 13px;
  color: #a0a0a0;
  margin-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 1px;
}
</style>
