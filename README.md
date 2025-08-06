# Git 分支检查工具

一个简洁的 Web 应用，用于检查 Git 仓库中分支的合并状态，支持多种 Git 平台的智能链接跳转。

## 功能特性

- 🔗 **仓库连接**: 支持本地路径和远程 SSH/HTTPS 仓库
- 📋 **分支管理**: 显示所有分支信息和提交历史
- 🔍 **合并检查**: 检查指定分支是否已合并到目标分支
- 🌐 **多平台支持**: 自动识别 GitLab、GitHub、阿里云 CodeUp 等平台
- 🔗 **智能链接**: 自动生成 MR/PR 和提交的可点击链接

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动应用

```bash
python app.py
```

访问 `http://localhost:5000`

## 项目结构

```
pycheck/
├── app.py              # Flask主应用
├── config.json         # 仓库和平台配置
├── requirements.txt    # Python依赖
├── templates/
│   └── index.html     # 前端页面
└── temp_repos/        # 临时仓库目录
```

## 配置说明

### 仓库配置

在 `config.json` 中添加常用仓库：

```json
{
  //  添加仓库
  "repositories": [
    {
      "name": "项目名称",
      "url": "git@codeup.aliyun.com:group/project.git",
      "type": "remote",
      "platform": "codeup.aliyun.com"
    }
  ],
  //  配置仓库的链接地址信息
  "platforms": {
    "codeup.aliyun.com": {
      "name": "阿里云CodeUp",
      "base_url": "https://codeup.aliyun.com",
      "merge_request_path": "/change/",
      "commit_path": "/commit/",
      "ssh_prefix": "git@codeup.aliyun.com:",
      "https_prefix": "https://codeup.aliyun.com/"
    }
  }
}
```

### 平台配置

支持的平台配置：

- **阿里云 CodeUp**: `codeup.aliyun.com`
- **GitLab**: `gitlab.com`
- **GitHub**: `github.com`

每个平台包含：

- `base_url`: 平台基础 URL
- `merge_request_path`: MR/PR 路径模板
- `commit_path`: 提交路径模板
- `ssh_prefix` / `https_prefix`: URL 前缀用于自动识别

## 使用方法

### 1. 连接仓库

- 选择预设仓库或手动输入路径/URL
- 支持格式：
  - 本地路径: `D:\code\project`
  - SSH: `git@platform.com:group/project.git`
  - HTTPS: `https://platform.com/group/project.git`

### 2. 检查分支合并状态

- **关键字**: 要检查的分支关键字（如 `feature`, `0811`）
- **目标分支**: 目标分支名（如 `master`, `prod`）

### 3. 查看结果

- 合并状态（已合并/未合并）
- 合并日期和提交人信息
- 可点击的 MR/PR 和提交链接

## 检测逻辑

使用 `git merge-base` 算法检查分支合并状态：

1. 获取源分支和目标分支的共同祖先
2. 判断源分支提交是否在目标分支历史中
3. 查找具体的合并提交和 MR/PR 信息
4. 支持 Fast-Forward 合并和直接推送检测

## 注意事项

- 使用 SSH URL 需要配置 SSH 密钥
- 远程仓库需要网络连接和访问权限
- 临时克隆的仓库存储在 `temp_repos/` 目录
