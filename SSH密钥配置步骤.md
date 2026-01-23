# SSH密钥配置步骤

## 已完成的步骤

✅ 1. 在当前Linux服务器生成了新的SSH密钥对
   - 私钥：`/root/.ssh/id_ed25519_prod`
   - 公钥：`/root/.ssh/id_ed25519_prod.pub`

✅ 2. 更新了SSH配置文件 `~/.ssh/config`

---

## 需要您执行的步骤

### 步骤1：将公钥添加到原服务器

**公钥内容**（请完整复制）：
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMaf3TW0YbCi68flx9PSAKRYaPQtIDS/W8kOhGIPigIT current-server-to-prod
```

**方法A：从Windows登录原服务器添加（推荐）**

```bash
# 1. 在Windows上通过SSH登录原服务器
ssh ecs-assist-user@121.43.126.173

# 2. 在原服务器上执行以下命令
mkdir -p ~/.ssh
chmod 700 ~/.ssh
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMaf3TW0YbCi68flx9PSAKRYaPQtIDS/W8kOhGIPigIT current-server-to-prod" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys

# 3. 退出原服务器
exit
```

**方法B：通过您现有的Windows SSH配置添加**

```bash
# 在Windows上执行（使用您现有的SSH密钥）
ssh my-ecs "mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMaf3TW0YbCi68flx9PSAKRYaPQtIDS/W8kOhGIPigIT current-server-to-prod' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

---

### 步骤2：验证SSH连接（在当前Linux服务器执行）

添加公钥后，在当前Linux服务器上测试连接：

```bash
# 测试SSH连接
ssh prod-server "echo 'Connection successful!' && pwd && whoami"

# 或使用别名
ssh my-ecs "echo 'Connection successful!' && pwd && whoami"
```

**预期输出**：
```
Connection successful!
/home/ecs-assist-user
ecs-assist-user
```

---

### 步骤3：获取原服务器信息（连接成功后执行）

```bash
# 查看原服务器上的项目路径
ssh prod-server "ls -la ~ | grep -E 'ai|wechat|server'"

# 查看是否有Git仓库
ssh prod-server "find ~ -maxdepth 2 -name '.git' -type d"

# 查看ai-factory路径（如果存在）
ssh prod-server "ls -la ~/ai-factory 2>/dev/null || echo 'ai-factory not found'"

# 查看wechat路径（如果存在）
ssh prod-server "ls -la ~/wechat* 2>/dev/null || echo 'wechat project not found'"
```

---

## 常见问题

### 问题1：无法登录原服务器

**原因**：可能需要密码或SSH密钥认证

**解决**：
1. 使用您Windows机器上现有的SSH密钥登录：
   ```bash
   # 在Windows上执行
   ssh ecs-assist-user@121.43.126.173
   ```

2. 如果需要密码，输入密码后添加公钥

### 问题2：添加公钥后仍无法连接

**原因**：SSH服务可能需要重启或authorized_keys权限问题

**解决**：
```bash
# 在原服务器上执行
ssh ecs-assist-user@121.43.126.173 << 'EOF'
# 检查authorized_keys权限
ls -la ~/.ssh/authorized_keys

# 修正权限
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh

# 检查SSH服务状态
systemctl status sshd
EOF
```

### 问题3：Permission denied (publickey)

**原因**：公钥未正确添加或密钥路径配置错误

**解决**：
```bash
# 检查SSH配置
cat ~/.ssh/config

# 检查密钥文件权限
ls -la ~/.ssh/id_ed25519_prod

# 修正权限
chmod 600 ~/.ssh/id_ed25519_prod
```

---

## 下一步

SSH连接建立成功后，我将：

1. ✅ 对比原服务器和当前服务器的代码结构
2. ✅ 识别同步遗漏或差异
3. ✅ 生成详细的差异报告
4. ✅ 评估是否需要修复wechat-workspace
5. ✅ 建立自动化同步机制

---

## 快速命令参考

**在当前Linux服务器上**：
```bash
# 测试连接
ssh prod-server "pwd"

# 执行远程命令
ssh prod-server "ls -la"

# 查看远程Git仓库
ssh prod-server "cd ~/ai-factory && git log --oneline -5"
```

**在原服务器上**（如果需要）：
```bash
# 查看authorized_keys内容
cat ~/.ssh/authorized_keys

# 删除旧密钥（如果需要）
vim ~/.ssh/authorized_keys

# 检查SSH日志
tail -f /var/log/auth.log | grep sshd
```

---

**请在完成步骤1和步骤2后告知我，我将立即进行代码对比。**
