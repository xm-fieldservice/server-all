# SSH持久连接建立指南

## 一、当前状态

```
服务器信息：
- 原开发服务器：121.43.126.173
- 用户名：ecs-assist-user
- 网络状态：✅ 可达（ping延迟33ms）
- SSH配置：❌ 缺少密钥或密码认证
```

## 二、建立SSH连接的方案

### 方案A：配置SSH密钥（推荐）

#### 步骤1：生成SSH密钥对

```bash
# 在当前服务器上生成新的SSH密钥
ssh-keygen -t rsa -b 4096 -f ~/.ssh/prod_server_key -N ""

# 生成的文件：
# ~/.ssh/prod_server_key      (私钥)
# ~/.ssh/prod_server_key.pub  (公钥)
```

#### 步骤2：复制公钥到原服务器

**方法1：使用ssh-copy-id（如果可用）**
```bash
ssh-copy-id -i ~/.ssh/prod_server_key.pub ecs-assist-user@121.43.126.173
```

**方法2：手动复制（如果没有ssh-copy-id）**
```bash
# 显示公钥内容
cat ~/.ssh/prod_server_key.pub

# 复制公钥内容，然后在原服务器上执行：
mkdir -p ~/.ssh
chmod 700 ~/.ssh
echo "ssh-rsa AAAA... [复制的内容] ecs-assist-user@current-server" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

#### 步骤3：配置SSH客户端

```bash
# 更新SSH配置文件
cat >> ~/.ssh/config << 'EOF'

Host prod-server
    HostName 121.43.126.173
    User ecs-assist-user
    IdentityFile ~/.ssh/prod_server_key
    StrictHostKeyChecking no
    ServerAliveInterval 60
    ServerAliveCountMax 3
EOF
```

#### 步骤4：测试连接

```bash
# 测试SSH连接
ssh prod-server "echo 'Connection successful!' && pwd && ls -la"

# 应该输出：
# Connection successful!
# /home/ecs-assist-user
# ...
```

### 方案B：使用密码认证（如果SSH密钥不可用）

#### 安装sshpass

```bash
# Ubuntu/Debian
apt-get update && apt-get install -y sshpass

# CentOS/RHEL
yum install -y sshpass

# 或者使用Python
pip3 install sshpass
```

#### 使用密码连接

```bash
# 直接连接
sshpass -p 'your_password' ssh ecs-assist-user@121.43.126.173 "pwd"

# 使用别名（更新SSH配置）
cat >> ~/.ssh/config << 'EOF'
Host prod-server-pwd
    HostName 121.43.126.173
    User ecs-assist-user
EOF

# 连接
sshpass -p 'your_password' ssh prod-server-pwd "pwd"
```

#### 安全提示

⚠️ **密码明文不安全**，建议：
1. 使用环境变量：`export SSH_PASS='your_password'`
2. 或使用密钥认证（方案A）

### 方案C：使用SSH跳板机（如果直接连接不可用）

```bash
# 通过跳板机连接
ssh -J jumpserver@jump-host:port ecs-assist-user@121.43.126.173

# 配置跳板机
cat >> ~/.ssh/config << 'EOF'
Host prod-server
    HostName 121.43.126.173
    User ecs-assist-user
    ProxyJump jumpuser@jumphost:jumpport
    IdentityFile ~/.ssh/prod_server_key
EOF
```

## 三、建立持久连接

### 1. SSH自动登录（免密）

使用方案A配置SSH密钥后，即可实现免密登录：

```bash
# 直接执行命令，无需输入密码
ssh prod-server "ls -la /home/ecs-assist-user"
ssh prod-server "cd /path/to/ai-factory && git log --oneline -5"
```

### 2. SSH隧道（端口转发）

```bash
# 本地端口转发（远程端口映射到本地）
ssh -L 8000:localhost:8001 prod-server

# 远程端口转发（本地端口映射到远程）
ssh -R 8000:localhost:8001 prod-server

# 动态端口转发（SOCKS代理）
ssh -D 1080 prod-server
```

### 3. SSH自动重连（autossh）

```bash
# 安装autossh
apt-get install -y autossh

# 使用autossh保持连接
autossh -M 0 -o "ServerAliveInterval 60" -o "ServerAliveCountMax 3" prod-server

# 后台运行
autossh -f -M 0 -o "ServerAliveInterval 60" -o "ServerAliveCountMax 3" prod-server
```

### 4. 定时同步脚本

创建同步脚本：`/root/scripts/sync_from_prod.sh`

```bash
#!/bin/bash
# 同步脚本：从原服务器拉取最新代码

LOG_FILE="/var/log/sync_from_prod.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$DATE] Starting sync from production server..." >> $LOG_FILE

# 1. 检查SSH连接
if ! ssh prod-server "echo 'SSH connection OK'" > /dev/null 2>&1; then
    echo "[$DATE] ERROR: SSH connection failed!" >> $LOG_FILE
    exit 1
fi

# 2. 拉取ai-factory最新代码
echo "[$DATE] Pulling ai-factory latest code..." >> $LOG_FILE
cd /root/ai-factory
git fetch origin
git pull origin dev-memory-system

# 3. 检查wechat-workspace（如果有）
if [ -d "/root/wechat-workspace/.git" ]; then
    echo "[$DATE] Pulling wechat-workspace latest code..." >> $LOG_FILE
    cd /root/wechat-workspace
    git fetch origin
    git pull origin wechat-project-main
else
    echo "[$DATE] WARNING: wechat-workspace is not a git repository!" >> $LOG_FILE
fi

# 4. 对比差异
echo "[$DATE] Checking for differences..." >> $LOG_FILE
cd /root/ai-factory
LOCAL_COMMITS=$(git rev-list --count HEAD..origin/dev-memory-system)
REMOTE_COMMITS=$(git rev-list --count origin/dev-memory-system..HEAD)

if [ $LOCAL_COMMITS -gt 0 ]; then
    echo "[$DATE] WARNING: Local has $LOCAL_COMMITS unpushed commits!" >> $LOG_FILE
fi

if [ $REMOTE_COMMITS -gt 0 ]; then
    echo "[$DATE] WARNING: Remote has $REMOTE_COMMITS new commits!" >> $LOG_FILE
fi

echo "[$DATE] Sync completed." >> $LOG_FILE
```

添加执行权限：
```bash
chmod +x /root/scripts/sync_from_prod.sh
```

### 5. 定时任务（cron）

```bash
# 编辑crontab
crontab -e

# 添加定时任务（每小时同步一次）
0 * * * * /root/scripts/sync_from_prod.sh >> /var/log/sync.log 2>&1

# 或（每30分钟同步一次）
*/30 * * * * /root/scripts/sync_from_prod.sh >> /var/log/sync.log 2>&1
```

### 6. 监控SSH连接状态

创建监控脚本：`/root/scripts/check_ssh_connection.sh`

```bash
#!/bin/bash
# 检查SSH连接状态

HOST="prod-server"
LOG_FILE="/var/log/ssh_connection.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

if ssh $HOST "echo 'OK'" > /dev/null 2>&1; then
    echo "[$DATE] SSH connection to $HOST is OK" >> $LOG_FILE
    exit 0
else
    echo "[$DATE] ERROR: SSH connection to $HOST failed!" >> $LOG_FILE
    # 发送告警邮件或其他通知
    exit 1
fi
```

添加到定时任务：
```bash
# 每5分钟检查一次
*/5 * * * * /root/scripts/check_ssh_connection.sh
```

## 四、常用SSH命令

### 远程命令执行

```bash
# 单条命令
ssh prod-server "ls -la"

# 多条命令
ssh prod-server "cd /home/ecs-assist-user && ls -la && pwd"

# 使用管道
ssh prod-server "cat /var/log/syslog | grep error | tail -20"
```

### 文件传输（scp）

```bash
# 上传文件到远程
scp /root/local_file.txt prod-server:/home/ecs-assist-user/

# 上传目录（递归）
scp -r /root/local_dir/ prod-server:/home/ecs-assist-user/

# 从远程下载文件
scp prod-server:/home/ecs-assist-user/remote_file.txt /root/

# 从远程下载目录
scp -r prod-server:/home/ecs-assist-user/remote_dir/ /root/
```

### 文件同步（rsync）

```bash
# 同步本地到远程
rsync -avz /root/ai-factory/ prod-server:/path/to/backup/

# 同步远程到本地
rsync -avz prod-server:/path/to/source/ /root/destination/

# 增量同步（只传输变化的部分）
rsync -avz --delete /root/ai-factory/ prod-server:/path/to/backup/
```

## 五、故障排查

### 问题1：SSH连接失败

**症状**：`ssh: connect to host 121.43.126.173 port 22: Connection refused`

**原因**：
1. SSH服务未运行
2. 防火墙阻止
3. 网络问题

**解决**：
```bash
# 检查网络
ping 121.43.126.173

# 检查端口是否开放
telnet 121.43.126.173 22
nc -zv 121.43.126.173 22

# 检查SSH服务（在原服务器上）
systemctl status sshd
```

### 问题2：认证失败

**症状**：`Permission denied (publickey,password)`

**原因**：
1. SSH密钥未正确配置
2. 用户名错误
3. 权限问题

**解决**：
```bash
# 检查密钥权限
ls -la ~/.ssh/prod_server_key
chmod 600 ~/.ssh/prod_server_key

# 检查authorized_keys权限
ssh prod-server "ls -la ~/.ssh/authorized_keys"
ssh prod-server "chmod 600 ~/.ssh/authorized_keys"

# 检查用户名
ssh -v ecs-assist-user@121.43.126.173 "pwd"
```

### 问题3：连接超时

**症状**：`ssh: connect to host 121.43.126.173 port 22: Connection timed out`

**原因**：
1. 网络延迟
2. 防火墙
3. 负载过高

**解决**：
```bash
# 增加超时时间
ssh -o ConnectTimeout=30 prod-server "pwd"

# 启用压缩
ssh -C prod-server "pwd"

# 保持连接活跃
ssh -o ServerAliveInterval=60 prod-server "pwd"
```

## 六、安全最佳实践

1. ✅ 使用SSH密钥而非密码
2. ✅ 定期轮换SSH密钥
3. ✅ 限制SSH访问IP
4. ✅ 禁用root登录（在原服务器上）
5. ✅ 使用SSH配置文件管理连接
6. ✅ 定期审计SSH访问日志

## 七、需要用户提供的信息

为了建立SSH连接，我需要：

1. **SSH认证信息**：
   - 是否有原服务器的SSH密钥？（.pem文件或类似）
   - 如果没有，是否知道原服务器的密码？

2. **原服务器信息**：
   - ai-factory在原服务器的绝对路径？
   - wechat项目在原服务器的绝对路径？
   - 是否还有其他需要同步的项目？

3. **网络和访问**：
   - 是否需要通过跳板机或VPN访问？
   - 是否有防火墙限制？

---

**建立SSH连接后，我将能够**：
- ✅ 实时对比原服务器和当前服务器的代码
- ✅ 检测代码同步遗漏或冲突
- ✅ 建立自动化同步机制
- ✅ 监控代码变更

**请提供SSH认证信息，我将立即建立持久连接。**
