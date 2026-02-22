<template>
  <div class="context-menu" :style="{ left: x + 'px', top: y + 'px' }">
    <div class="menu-item" @click="$emit('add')">添加子节点</div>
    <div class="menu-item" @click="$emit('edit')">编辑</div>
    <div class="menu-item danger" @click="$emit('delete')">删除</div>
    <div class="menu-divider"></div>
    <div class="menu-item" @click="$emit('close')">取消</div>
  </div>
</template>

<script setup>
defineProps({
  x: Number,
  y: Number,
  node: Object
})

defineEmits(['close', 'add', 'edit', 'delete'])
</script>

<style scoped>
.context-menu {
  position: fixed;
  background: #2d2d30;
  border: 1px solid #3e3e42;
  border-radius: 4px;
  padding: 4px 0;
  min-width: 120px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.4);
  z-index: 1000;
}

.menu-item {
  padding: 8px 16px;
  cursor: pointer;
  color: #d4d4d4;
  font-size: 13px;
}

.menu-item:hover {
  background: #094771;
}

.menu-item.danger {
  color: #f48771;
}

.menu-divider {
  height: 1px;
  background: #3e3e42;
  margin: 4px 0;
}
</style>
