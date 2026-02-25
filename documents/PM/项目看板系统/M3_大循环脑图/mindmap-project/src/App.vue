<template>
  <div id="app">
    <DevLab />
  </div>
</template>

<script setup>
import DevLab from './views/DevLab.vue'
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background-color: #1e1e1e;
  color: #d4d4d4;
  min-height: 100vh;
}

#app {
  min-height: 100vh;
}
</style>
