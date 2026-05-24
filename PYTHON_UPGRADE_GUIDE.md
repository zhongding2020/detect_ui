# Python 3.12+ 升级指南

## 当前环境信息
- **操作系统**: Ubuntu 20.04.6 LTS (Focal Fossa)
- **当前Python版本**: Python 3.8.10
- **限制**: 当前沙箱环境无sudo权限，文件系统为只读

---

## 方案一：在您的本地机器上升级（推荐）

### 1. Ubuntu/Debian 系统升级

```bash
# 更新包列表
sudo apt update

# 安装 deadsnakes PPA（提供更新的Python版本）
sudo apt install software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update

# 安装 Python 3.12
sudo apt install python3.12 python3.12-dev python3.12-venv

# 验证安装
python3.12 --version

# 可选：设置为默认Python（谨慎操作）
# sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.8 1
# sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 2
# sudo update-alternatives --config python3
```

### 2. 使用 pyenv（推荐用于开发环境）

```bash
# 安装依赖
sudo apt update
sudo apt install -y make build-essential libssl-dev zlib1g-dev \
libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm \
libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev

# 安装 pyenv
curl https://pyenv.run | bash

# 添加到 shell 配置文件 (~/.bashrc 或 ~/.zshrc)
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc

# 重新加载配置
source ~/.bashrc

# 安装 Python 3.12
pyenv install 3.12.0

# 设置全局版本
pyenv global 3.12.0

# 验证
python --version
```

### 3. 使用 Conda

```bash
# 下载并安装 Miniconda
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh

# 创建 Python 3.12 环境
conda create -n py312 python=3.12
conda activate py312

# 验证
python --version
```

---

## 方案二：macOS 系统升级

### 使用 Homebrew
```bash
# 安装 Homebrew（如果未安装）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 安装 Python 3.12
brew install python@3.12

# 验证
python3.12 --version
```

### 使用 pyenv（推荐）
```bash
# 安装 Homebrew 依赖
brew install pyenv

# 安装 Python 3.12
pyenv install 3.12.0
pyenv global 3.12.0
```

---

## 方案三：Windows 系统升级

1. 访问 [Python 官网](https://www.python.org/downloads/)
2. 下载 Python 3.12+ 安装程序
3. 运行安装程序，**务必勾选 "Add Python to PATH"**
4. 验证安装：
   ```cmd
   python --version
   ```

---

## 验证安装成功

安装完成后，运行以下命令验证：

```bash
python3.12 --version
# 或
python --version
```

应该显示类似：
```
Python 3.12.x
```

---

## 安装 PyQt5 并运行界面程序

安装好 Python 3.12 后：

```bash
# 进入项目目录
cd /path/to/trae_projects

# 创建虚拟环境（推荐）
python3.12 -m venv venv
source venv/bin/activate  # Linux/macOS
# 或
.\venv\Scripts\activate  # Windows

# 安装依赖
pip install PyQt5

# 运行界面程序
python bearing_defect_detection.py
```
