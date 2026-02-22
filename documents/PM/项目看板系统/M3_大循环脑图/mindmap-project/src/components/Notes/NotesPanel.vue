<template>
  <div class="notes-panel">
    <div class="notes-list">
      <div 
        v-for="note in notes" 
        :key="note.id" 
        :class="['note-item', { active: activeNote?.id === note.id }]"
        @click="activeNote = note"
      >
        <div class="note-title">{{ note.title }}</div>
        <div class="note-preview">{{ note.content.slice(0, 50) }}...</div>
      </div>
    </div>
    <div class="note-editor" v-if="activeNote">
      <input v-model="activeNote.title" placeholder="笔记标题">
      <textarea v-model="activeNote.content" placeholder="笔记内容..."></textarea>
      <button class="save-btn" @click="saveNote">保存到脑图</button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const notes = ref([
  { id: 1, title: '项目启动笔记', content: '项目启动会议记录...' },
  { id: 2, title: '需求分析', content: '用户需求整理...' }
])

const activeNote = ref(null)

function saveNote() {
  console.log('保存笔记到脑图:', activeNote.value)
  alert('笔记已保存到脑图（模拟）')
}
</script>

<style scoped>
.notes-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.notes-list {
  flex: 1;
  overflow-y: auto;
}

.note-item {
  padding: 10px 12px;
  border-bottom: 1px solid #3e3e42;
  cursor: pointer;
}

.note-item:hover {
  background: rgba(255,255,255,0.05);
}

.note-item.active {
  background: rgba(78, 201, 176, 0.1);
  border-left: 2px solid #4ec9b0;
}

.note-title {
  font-size: 13px;
  color: #d4d4d4;
  margin-bottom: 4px;
}

.note-preview {
  font-size: 11px;
  color: #a0a0a0;
}

.note-editor {
  border-top: 1px solid #3e3e42;
  padding-top: 12px;
}

.note-editor input {
  width: 100%;
  padding: 8px;
  background: #3c3c3c;
  border: 1px solid #3e3e42;
  border-radius: 4px;
  color: #d4d4d4;
  font-size: 13px;
  margin-bottom: 8px;
}

.note-editor textarea {
  width: 100%;
  height: 80px;
  padding: 8px;
  background: #3c3c3c;
  border: 1px solid #3e3e42;
  border-radius: 4px;
  color: #d4d4d4;
  font-size: 13px;
  resize: none;
}

.save-btn {
  margin-top: 8px;
  padding: 8px 16px;
  background: #4ec9b0;
  border: none;
  border-radius: 4px;
  color: #1e1e1e;
  font-size: 12px;
  cursor: pointer;
}
</style>
