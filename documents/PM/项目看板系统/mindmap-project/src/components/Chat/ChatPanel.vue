<template>
  <div class="chat-panel">
    <div class="messages">
      <div v-for="(msg, index) in messages" :key="index" :class="['message', msg.role]">
        <div class="message-content">{{ msg.content }}</div>
      </div>
    </div>
    <div class="input-area">
      <input 
        v-model="input" 
        placeholder="输入问题..." 
        @keyup.enter="handleSend"
      >
      <button @click="handleSend">发送</button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const messages = ref([
  { role: 'assistant', content: '你好！我是AI助手，可以帮你分析项目、管理任务。' }
])

const input = ref('')

function handleSend() {
  if (!input.value.trim()) return
  
  messages.value.push({
    role: 'user',
    content: input.value
  })
  
  const userInput = input.value
  input.value = ''
  
  setTimeout(() => {
    messages.value.push({
      role: 'assistant',
      content: `这是一个模拟回复："${userInput}"。\n\n在实际环境中，这里会显示Agent的处理结果。`
    })
  }, 1000)
}
</script>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.message {
  margin-bottom: 12px;
}

.message.user {
  text-align: right;
}

.message-content {
  display: inline-block;
  max-width: 80%;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.5;
}

.message.user .message-content {
  background: #0e639c;
  color: white;
}

.message.assistant .message-content {
  background: #3c3c3c;
  color: #d4d4d4;
  text-align: left;
}

.input-area {
  display: flex;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid #3e3e42;
}

.input-area input {
  flex: 1;
  padding: 8px 12px;
  background: #3c3c3c;
  border: 1px solid #3e3e42;
  border-radius: 4px;
  color: #d4d4d4;
  font-size: 13px;
}

.input-area input:focus {
  outline: none;
  border-color: #4ec9b0;
}

.input-area button {
  padding: 8px 16px;
  background: #4ec9b0;
  border: none;
  border-radius: 4px;
  color: #1e1e1e;
  font-size: 13px;
  cursor: pointer;
}

.input-area button:hover {
  background: #45b7a1;
}
</style>
