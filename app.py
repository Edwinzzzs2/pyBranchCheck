from flask import Flask, render_template, request, jsonify
import os
import tempfile
import shutil
import json
from datetime import datetime
import re

# 延迟导入git模块，避免在没有Git环境时导入失败
git = None

# 设置全局编码
import sys
import webbrowser
import threading
import time
import subprocess
from pathlib import Path

def setup_git_environment():
    """设置Git环境变量，确保在没有Python环境的机器上也能运行"""
    global git
    
    if sys.platform.startswith('win'):
        os.environ['GIT_PYTHON_ENCODING'] = 'utf-8'
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        
        # 检查是否为打包后的exe运行
        is_exe = getattr(sys, 'frozen', False)
        if is_exe:
            # 设置Git相关环境变量
            os.environ['GIT_PYTHON_REFRESH'] = 'quiet'
            
            # 尝试找到Git可执行文件
            git_paths = [
                r'C:\Program Files\Git\bin\git.exe',
                r'C:\Program Files (x86)\Git\bin\git.exe',
                r'C:\Git\bin\git.exe',
                'git.exe'  # 如果Git在PATH中
            ]
            
            git_found = False
            for git_path in git_paths:
                try:
                    if os.path.exists(git_path) or git_path == 'git.exe':
                        # 测试Git是否可用
                        result = subprocess.run([git_path, '--version'], 
                                               capture_output=True, text=True, timeout=5)
                        if result.returncode == 0:
                            if git_path != 'git.exe':
                                # 将Git目录添加到PATH
                                git_dir = str(Path(git_path).parent)
                                current_path = os.environ.get('PATH', '')
                                if git_dir not in current_path:
                                    os.environ['PATH'] = f"{git_dir};{current_path}"
                            git_found = True
                            break
                except Exception:
                    continue
            
            if not git_found:
                raise Exception("未找到Git，请确保已安装Git并添加到系统PATH中")
    
    # 尝试导入git模块
    try:
        import git as git_module
        git = git_module
        return True
    except Exception as e:
        raise Exception(f"Git模块导入失败: {str(e)}")

# Git环境将在主函数中初始化

app = Flask(__name__)

def get_config_path():
    """获取配置文件路径，优先使用外部配置文件"""
    # 检查是否为打包后的exe运行
    is_exe = getattr(sys, 'frozen', False)
    
    if is_exe:
        # 打包后的exe，配置文件在exe同目录
        exe_dir = os.path.dirname(sys.executable)
        external_config = os.path.join(exe_dir, 'config.json')
        
        # 优先使用外部配置文件
        if os.path.exists(external_config):
            return external_config
        
        # 如果外部配置文件不存在，使用内置配置文件
        internal_config = os.path.join(os.path.dirname(__file__), 'config.json')
        return internal_config
    else:
        # 开发环境，使用项目目录下的配置文件
        return os.path.join(os.path.dirname(__file__), 'config.json')

def load_config():
    """加载配置文件"""
    try:
        config_path = get_config_path()
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"加载配置文件失败: {e}")
        return {"repositories": [], "platforms": {}}

def save_config(config):
    """保存配置文件"""
    try:
        config_path = get_config_path()
        
        # 确保目录存在
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"保存配置文件失败: {e}")
        return False

class GitBranchChecker:
    def __init__(self, repo_input):
        self.repo_input = repo_input
        self.repo = None
        self.is_remote = self._is_remote_url(repo_input)
        self.local_path = None
        self.config = load_config()
        self.current_repo_config = None
        self.platform_config = None
        self._identify_repo_platform()
        
    def _is_remote_url(self, url):
        """判断是否为远程仓库URL"""
        return url.startswith(('git@', 'https://', 'http://')) or '.git' in url
    
    def _identify_repo_platform(self):
        """识别当前仓库的平台配置"""
        try:
            # 首先尝试从配置文件中的repositories列表匹配
            for repo in self.config.get('repositories', []):
                if repo.get('url') == self.repo_input:
                    self.current_repo_config = repo
                    platform_key = repo.get('platform')
                    if platform_key and platform_key in self.config.get('platforms', {}):
                        self.platform_config = self.config['platforms'][platform_key]
                    return
            
            # 如果没有在配置中找到，尝试根据URL自动识别平台
            self._auto_identify_platform()
        except Exception as e:
            print(f"识别仓库平台时出错: {e}")
            self._set_default_platform()
    
    def _auto_identify_platform(self):
        """根据URL自动识别平台"""
        try:
            platforms = self.config.get('platforms', {})
            
            for platform_key, platform_info in platforms.items():
                ssh_prefix = platform_info.get('ssh_prefix', '')
                https_prefix = platform_info.get('https_prefix', '')
                
                if (ssh_prefix and self.repo_input.startswith(ssh_prefix)) or \
                   (https_prefix and self.repo_input.startswith(https_prefix)) or \
                   platform_key in self.repo_input:
                    self.platform_config = platform_info
                    return
            
            # 如果都没匹配到，设置默认平台
            self._set_default_platform()
        except Exception as e:
            print(f"自动识别平台时出错: {e}")
            self._set_default_platform()
    
    def _set_default_platform(self):
        """设置默认平台配置"""
        self.platform_config = {
            "name": "阿里云Code",
            "base_url": "https://code.aliyun.com",
            "merge_request_path": "/-/merge_requests/",
            "commit_path": "/-/commit/",
            "ssh_prefix": "git@code.aliyun.com:",
            "https_prefix": "https://code.aliyun.com/"
        }
        
    def connect_repo(self):
        """连接到Git仓库"""
        # 设置多个环境变量来解决编码问题
        os.environ['GIT_PYTHON_ENCODING'] = 'utf-8'
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        os.environ['LC_ALL'] = 'C.UTF-8'
        try:
            if self.is_remote:
                # 处理远程仓库
                return self._clone_or_fetch_remote()
            else:
                # 处理本地仓库
                if not os.path.exists(self.repo_input):
                    return False, "仓库路径不存在"
                
                self.repo = git.Repo(self.repo_input)
                self.local_path = self.repo_input
                return True, "本地仓库连接成功"
        except git.exc.InvalidGitRepositoryError:
            return False, "不是有效的Git仓库"
        except Exception as e:
            return False, f"连接失败: {str(e)}"
    
    def _clone_or_fetch_remote(self):
        """克隆或更新远程仓库"""
        try:
            # 从URL提取仓库名
            repo_name = self.repo_input.split('/')[-1].replace('.git', '')
            temp_dir = os.path.join(os.getcwd(), 'temp_repos')
            self.local_path = os.path.join(temp_dir, repo_name)
            
            # 创建临时目录
            os.makedirs(temp_dir, exist_ok=True)
            
            if os.path.exists(self.local_path):
                # 如果本地已存在，尝试更新
                try:
                    self.repo = git.Repo(self.local_path)
                    # 设置git配置以处理编码问题
                    with self.repo.config_writer() as git_config:
                        git_config.set_value("core", "quotepath", "false")
                    
                    # 获取所有远程分支
                    for remote in self.repo.remotes:
                        try:
                            # 使用更安全的 fetch 方式
                            remote.fetch(verbose=False)
                        except (UnicodeDecodeError, git.exc.GitCommandError) as e:
                            # 忽略编码错误和命令错误，继续执行
                            print(f"Fetch warning (ignored): {str(e)}")
                            pass
                    return True, f"远程仓库已更新到本地: {self.local_path}"
                except:
                    # 如果更新失败，删除重新克隆
                    import shutil
                    shutil.rmtree(self.local_path)
            
            # 克隆仓库
            self.repo = git.Repo.clone_from(self.repo_input, self.local_path)
            # 设置git配置以处理编码问题
            with self.repo.config_writer() as git_config:
                git_config.set_value("core", "quotepath", "false")
            
            return True, f"远程仓库已克隆到本地: {self.local_path}"
            
        except git.exc.GitCommandError as e:
            if "Permission denied" in str(e) or "authentication" in str(e).lower():
                return False, "SSH认证失败，请确保您的SSH密钥已配置并有权限访问该仓库"
            return False, f"Git操作失败: {str(e)}"
        except UnicodeDecodeError:
            return False, "Git操作编码错误，但仓库可能已成功连接"
        except Exception as e:
            return False, f"克隆远程仓库失败: {str(e)}"
    
    def get_all_branches(self):
        """获取所有分支信息"""
        if not self.repo:
            return []
        
        branches = []
        try:
            # 获取本地分支
            for branch in self.repo.branches:
                commit = branch.commit
                branches.append({
                    'name': branch.name,
                    'type': 'local',
                    'last_commit': commit.hexsha[:8],
                    'last_commit_date': datetime.fromtimestamp(commit.committed_date).strftime('%Y-%m-%d %H:%M:%S'),
                    'last_commit_timestamp': commit.committed_date,  # 用于排序
                    'author_name': commit.author.name,
                    'author_email': commit.author.email,
                    'commit_message': commit.message.strip().split('\n')[0]
                })
            
            # 获取远程分支
            for remote in self.repo.remotes:
                for ref in remote.refs:
                    if ref.name != f"{remote.name}/HEAD":
                        branch_name = ref.name.replace(f"{remote.name}/", "")
                        # 避免重复显示已存在的本地分支
                        if not any(b['name'] == branch_name and b['type'] == 'local' for b in branches):
                            try:
                                commit = ref.commit
                                branches.append({
                                    'name': branch_name,
                                    'type': f'remote ({remote.name})',
                                    'last_commit': commit.hexsha[:8],
                                    'last_commit_date': datetime.fromtimestamp(commit.committed_date).strftime('%Y-%m-%d %H:%M:%S'),
                                    'last_commit_timestamp': commit.committed_date,  # 用于排序
                                    'author_name': commit.author.name,
                                    'author_email': commit.author.email,
                                    'commit_message': commit.message.strip().split('\n')[0]
                                })
                            except:
                                continue
            
            # 按最后提交时间倒序排列
            branches.sort(key=lambda x: x['last_commit_timestamp'], reverse=True)
            
            # 添加序号并移除排序用的时间戳字段
            for i, branch in enumerate(branches, 1):
                branch['index'] = i
                del branch['last_commit_timestamp']
                
        except Exception as e:
            print(f"获取分支信息时出错: {e}")
        
        return branches
    
    def check_branch_merge_status(self, keyword, target_branch):
        """检查包含关键字的分支是否合并到目标分支"""
        if not self.repo:
            return []
        
        results = []
        try:
            # 获取GitLab基础URL和项目路径
            gitlab_base_url = self._get_gitlab_base_url()
            project_path = self._get_project_path()
            
            # 获取所有分支（本地和远程）获取所有分支
            all_branches = []
            
            # 本地分支
            for branch in self.repo.branches:
                all_branches.append(branch.name)
            
            # 远程分支
            for remote in self.repo.remotes:
                for ref in remote.refs:
                    if ref.name != f"{remote.name}/HEAD":
                        branch_name = ref.name.replace(f"{remote.name}/", "")
                        all_branches.append(branch_name)
            
            # 过滤包含关键字的分支
            keyword_branches = [b for b in set(all_branches) if keyword in b]
            
            for branch_name in keyword_branches:
                try:
                    # 检查分支是否存在于目标分支的历史中
                    merge_info = self.check_merge_info(branch_name, target_branch)
                    
                    # 获取分支的最后提交人信息
                    author_info = self.get_branch_author_info(branch_name)
                    
                    results.append({
                        'branch_name': branch_name,
                        'is_merged': merge_info['is_merged'],
                        'merge_date': merge_info['merge_date'],
                        'merge_commit': merge_info['merge_commit'],
                        'merge_author': merge_info.get('merge_author', '未知'),
                        'author_name': author_info['author_name'],
                        'author_email': author_info['author_email'],
                        'gitlab_url': gitlab_base_url,
                        'project_path': project_path,
                        'platform_config': self.platform_config,
                        'mr_id': merge_info.get('mr_id'),
                        'commit_hash': merge_info.get('commit_hash')
                    })
                except Exception as e:
                    results.append({
                        'branch_name': branch_name,
                        'is_merged': False,
                        'merge_date': None,
                        'merge_commit': None,
                        'author_name': None,
                        'author_email': None,
                        'error': str(e)
                    })
        
        except Exception as e:
            print(f"检查分支合并状态时出错: {e}")
        
        # 按合并日期倒序排序（已合并的在前，未合并的在后）
        def sort_key(result):
            if result.get('is_merged') and result.get('merge_date'):
                try:
                    # 将日期字符串转换为datetime对象用于排序
                    return (1, datetime.strptime(result['merge_date'], '%Y-%m-%d %H:%M:%S'))
                except:
                    return (1, datetime.min)  # 如果日期解析失败，放在已合并的最后
            else:
                return (0, datetime.min)  # 未合并的放在最后
        
        results.sort(key=sort_key, reverse=True)
        
        return results
    
    def get_branch_author_info(self, branch_name):
        """获取分支的最后提交人信息"""
        try:
            # 尝试获取分支的最后一次提交
            branch_commit = None
            try:
                branch_commit = self.repo.heads[branch_name].commit
            except:
                # 尝试远程分支
                for remote in self.repo.remotes:
                    try:
                        branch_commit = getattr(remote.refs, branch_name).commit
                        break
                    except:
                        continue
            
            if branch_commit:
                return {
                    'author_name': branch_commit.author.name,
                    'author_email': branch_commit.author.email
                }
            else:
                return {'author_name': '未知', 'author_email': '未知'}
                
        except Exception as e:
            return {'author_name': '未知', 'author_email': '未知'}
    
    def check_merge_info(self, source_branch, target_branch):
        """检查具体的合并信息 - 优化版本"""
        try:
            # 获取目标分支引用
            target_ref = self._get_branch_ref(target_branch)
            if not target_ref:
                return {'is_merged': False, 'merge_date': None, 'merge_commit': None}
            
            # 获取源分支的最后一次提交ID
            source_commit = self._get_branch_last_commit(source_branch)
            if not source_commit:
                return {'is_merged': False, 'merge_date': None, 'merge_commit': None}
            
            source_commit_id = source_commit.hexsha
            print(f"源分支 {source_branch} 最后提交ID: {source_commit_id[:8]}")
            
            # 使用git命令直接查找提交是否在目标分支中
            try:
                # 使用 git merge-base 检查是否已合并
                merge_base = self.repo.git.merge_base(source_commit_id, target_ref.commit.hexsha)
                
                # 如果merge-base等于源分支的提交，说明已经合并
                if merge_base == source_commit_id:
                    # 查找包含此提交的合并提交
                    merge_info = self._find_merge_commit_efficient(source_commit_id, target_ref, source_branch)
                    if merge_info:
                        return merge_info
                    
                    # 如果没找到合并提交，可能是fast-forward或直接推送
                    return {
                        'is_merged': True,
                        'merge_date': datetime.fromtimestamp(source_commit.committed_date).strftime('%Y-%m-%d %H:%M:%S'),
                        'merge_commit': f"{source_commit_id[:8]} (直接合并)",
                        'merge_author': source_commit.author.name,
                        'mr_id': None,
                        'commit_hash': source_commit_id[:8]
                    }
                else:
                    return {'is_merged': False, 'merge_date': None, 'merge_commit': None}
                    
            except Exception as e:
                print(f"Git命令执行失败: {e}")
                return {'is_merged': False, 'merge_date': None, 'merge_commit': None}
                
        except Exception as e:
            print(f"检查合并信息时出错: {e}")
            return {'is_merged': False, 'merge_date': None, 'merge_commit': None}
    
    def _get_branch_ref(self, branch_name):
        """获取分支引用"""
        try:
            # 先尝试本地分支
            return self.repo.heads[branch_name]
        except:
            # 再尝试远程分支
            for remote in self.repo.remotes:
                try:
                    return getattr(remote.refs, branch_name)
                except:
                    continue
            return None
    
    def _get_branch_last_commit(self, branch_name):
        """获取分支的最后一次提交"""
        branch_ref = self._get_branch_ref(branch_name)
        return branch_ref.commit if branch_ref else None
    
    def _find_merge_commit_efficient(self, source_commit_id, target_ref, source_branch):
        """高效查找合并提交"""
        try:
            # 使用git log查找包含特定提交的合并提交
            # 限制搜索范围，只查看最近的合并提交
            log_output = self.repo.git.log(
                target_ref.commit.hexsha,
                '--merges',
                '--grep=' + source_branch,
                '--format=%H|%ct|%an|%s',
                '-n', '50'  # 只查看最近50个合并提交
            )
            
            if log_output:
                for line in log_output.split('\n'):
                    if line.strip():
                        parts = line.split('|', 3)
                        if len(parts) >= 4:
                            commit_hash, timestamp, author, message = parts
                            
                            # 检查这个合并提交是否包含我们的源提交
                            try:
                                # 使用git命令检查源提交是否在这个合并提交的历史中
                                self.repo.git.merge_base('--is-ancestor', source_commit_id, commit_hash)
                                
                                # 尝试从提交消息中提取Merge Request ID
                                mr_id = self._extract_merge_request_id(message)
                                if mr_id:
                                    merge_commit_display = f"{mr_id} ({commit_hash[:8]})"
                                else:
                                    merge_commit_display = f"{commit_hash[:8]} (合并提交)"
                                
                                return {
                                    'is_merged': True,
                                    'merge_date': datetime.fromtimestamp(int(timestamp)).strftime('%Y-%m-%d %H:%M:%S'),
                                    'merge_commit': merge_commit_display,
                                    'merge_author': author,
                                    'mr_id': mr_id,
                                    'commit_hash': commit_hash[:8]
                                }
                            except:
                                continue
            
            # 如果没找到合并提交，尝试查找直接包含源提交的提交
            try:
                log_output = self.repo.git.log(
                    target_ref.commit.hexsha,
                    '--format=%H|%ct|%an',
                    '--grep=' + source_commit_id[:8],
                    '-n', '10'
                )
                
                if log_output:
                    for line in log_output.split('\n'):
                        if line.strip():
                            parts = line.split('|', 2)
                            if len(parts) >= 3:
                                commit_hash, timestamp, author = parts
                                if commit_hash == source_commit_id:
                                    return {
                                        'is_merged': True,
                                        'merge_date': datetime.fromtimestamp(int(timestamp)).strftime('%Y-%m-%d %H:%M:%S'),
                                        'merge_commit': f"{commit_hash[:8]} (直接提交)",
                                        'merge_author': author,
                                        'mr_id': None,
                                        'commit_hash': commit_hash[:8]
                                    }
            except:
                pass
            
            return None
            
        except Exception as e:
            print(f"查找合并提交时出错: {e}")
            return None
    
    def _get_gitlab_base_url(self):
        """获取平台基础URL"""
        if self.platform_config:
            return self.platform_config.get('base_url', 'https://gitlab.com')
        return "https://gitlab.com"
    
    def _get_project_path(self):
        """获取项目路径，用于生成完整的链接"""
        try:
            if not self.platform_config:
                return ""
            
            for remote in self.repo.remotes:
                url = remote.url
                ssh_prefix = self.platform_config.get('ssh_prefix', '')
                https_prefix = self.platform_config.get('https_prefix', '')
                
                if ssh_prefix and url.startswith(ssh_prefix):
                    # SSH格式: git@platform.com:group/project.git
                    path_part = url.replace(ssh_prefix, '').replace('.git', '')
                    return f"/{path_part}"
                elif https_prefix and url.startswith(https_prefix):
                    # HTTPS格式: https://platform.com/group/project.git
                    path_part = url.replace(https_prefix, '').replace('.git', '')
                    if not path_part.startswith('/'):
                        path_part = f"/{path_part}"
                    return path_part
            
            return ""
        except Exception as e:
            print(f"获取项目路径时出错: {e}")
            return ""
    
    def _extract_merge_request_id(self, commit_message):
        """从提交消息中提取Merge Request ID"""
        import re
        
        # 常见的MR ID模式
        patterns = [
            r'merge request !(\d+)',  # GitLab: merge request !123
            r'!(\d+)',                # GitLab: !123
            r'pull request #(\d+)',   # GitHub: pull request #123
            r'#(\d+)',                # GitHub: #123
            r'PR (\d+)',              # Azure DevOps: PR 123
            r'pr (\d+)',              # Azure DevOps: pr 123
        ]
        
        for pattern in patterns:
            match = re.search(pattern, commit_message, re.IGNORECASE)
            if match:
                mr_number = match.group(1)
                # 根据模式返回相应的格式
                if 'pull request' in pattern or '#' in pattern:
                    return f"#{mr_number}"
                elif 'PR' in pattern or 'pr' in pattern:
                    return f"PR {mr_number}"
                else:
                    return f"!{mr_number}"
        
        return None


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/config')
def get_config():
    """获取配置的仓库列表"""
    try:
        config = load_config()
        return jsonify({
            'success': True,
            'repositories': config.get('repositories', []),
            'platforms': config.get('platforms', {}),
            'config_path': get_config_path()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/config/save', methods=['POST'])
def save_config_api():
    """保存配置"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': '请求数据格式错误'})
        
        # 验证配置数据格式
        if 'repositories' not in data or 'platforms' not in data:
            return jsonify({'success': False, 'message': '配置数据格式错误'})
        
        success = save_config(data)
        if success:
            return jsonify({'success': True, 'message': '配置保存成功'})
        else:
            return jsonify({'success': False, 'message': '配置保存失败'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'保存失败: {str(e)}'})

@app.route('/api/config/repository', methods=['POST'])
def add_repository():
    """添加仓库配置"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': '请求数据格式错误'})
        
        name = data.get('name', '').strip()
        url = data.get('url', '').strip()
        repo_type = data.get('type', 'ssh')
        platform = data.get('platform', '')
        
        if not name or not url:
            return jsonify({'success': False, 'message': '仓库名称和URL不能为空'})
        
        config = load_config()
        
        # 检查是否已存在相同名称或URL的仓库
        for repo in config.get('repositories', []):
            if repo.get('name') == name:
                return jsonify({'success': False, 'message': f'仓库名称 "{name}" 已存在'})
            if repo.get('url') == url:
                return jsonify({'success': False, 'message': f'仓库URL已存在'})
        
        # 添加新仓库
        new_repo = {
            'name': name,
            'url': url,
            'type': repo_type,
            'platform': platform
        }
        
        if 'repositories' not in config:
            config['repositories'] = []
        config['repositories'].append(new_repo)
        
        success = save_config(config)
        if success:
            return jsonify({'success': True, 'message': '仓库添加成功', 'repository': new_repo})
        else:
            return jsonify({'success': False, 'message': '仓库添加失败'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'添加失败: {str(e)}'})

@app.route('/api/config/repository/<int:index>', methods=['DELETE'])
def delete_repository(index):
    """删除仓库配置"""
    try:
        config = load_config()
        repositories = config.get('repositories', [])
        
        if index < 0 or index >= len(repositories):
            return jsonify({'success': False, 'message': '仓库索引无效'})
        
        deleted_repo = repositories.pop(index)
        success = save_config(config)
        
        if success:
            return jsonify({'success': True, 'message': f'仓库 "{deleted_repo.get("name", "")}" 删除成功'})
        else:
            return jsonify({'success': False, 'message': '仓库删除失败'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'})

@app.route('/api/config/platform', methods=['POST'])
def add_platform():
    """添加平台配置"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': '请求数据格式错误'})
        
        platform_key = data.get('key', '').strip()
        platform_config = data.get('config', {})
        
        if not platform_key:
            return jsonify({'success': False, 'message': '平台标识不能为空'})
        
        required_fields = ['name', 'base_url', 'merge_request_path', 'commit_path', 'ssh_prefix', 'https_prefix']
        for field in required_fields:
            if field not in platform_config or not platform_config[field].strip():
                return jsonify({'success': False, 'message': f'平台配置字段 "{field}" 不能为空'})
        
        config = load_config()
        
        if 'platforms' not in config:
            config['platforms'] = {}
        
        config['platforms'][platform_key] = platform_config
        
        success = save_config(config)
        if success:
            return jsonify({'success': True, 'message': '平台配置添加成功'})
        else:
            return jsonify({'success': False, 'message': '平台配置添加失败'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'添加失败: {str(e)}'})

@app.route('/api/connect', methods=['POST'])
def connect_repo():
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': '请求数据格式错误'})
            
        repo_input = data.get('repo_input', '')
        
        if not repo_input:
            return jsonify({'success': False, 'message': '请输入仓库路径或URL'})
        
        checker = GitBranchChecker(repo_input)
        success, message = checker.connect_repo()
        
        if success:
            branches = checker.get_all_branches()
            return jsonify({
                'success': True, 
                'message': message,
                'branches': branches,
                'local_path': checker.local_path
            })
        else:
            return jsonify({'success': False, 'message': message})
            
    except Exception as e:
        print(f"连接仓库时发生错误: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False, 
            'message': f'连接失败: {str(e)}'
        })

@app.route('/api/check_merge', methods=['POST'])
def check_merge():
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': '请求数据格式错误'})
            
        repo_input = data.get('repo_input', '')
        keyword = data.get('keyword', '')
        target_branch = data.get('target_branch', '')
        
        if not all([repo_input, keyword, target_branch]):
            return jsonify({'success': False, 'message': '请填写所有必要信息'})
        
        checker = GitBranchChecker(repo_input)
        success, message = checker.connect_repo()
        
        if not success:
            return jsonify({'success': False, 'message': message})
        
        results = checker.check_branch_merge_status(keyword, target_branch)
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        print(f"检查分支合并状态时发生错误: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False, 
            'message': f'检查失败: {str(e)}'
        })

def open_browser(port=5000):
    """延迟打开浏览器"""
    time.sleep(1.5)  # 等待服务器启动
    webbrowser.open(f'http://localhost:{port}')

def find_available_port(start_port=5000, max_attempts=10):
    """查找可用端口"""
    import socket
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    return None

def close_existing_processes():
    """关闭已存在的pyBranchCheck进程"""
    try:
        import psutil
        current_pid = os.getpid()
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] and 'pyBranchCheck' in proc.info['name']:
                    if proc.info['pid'] != current_pid:
                        proc.terminate()
                        print(f"已关闭之前的进程: PID {proc.info['pid']}")
                elif proc.info['cmdline']:
                    cmdline = ' '.join(proc.info['cmdline'])
                    if 'app.py' in cmdline and 'pyBranchCheck' in cmdline:
                        if proc.info['pid'] != current_pid:
                            proc.terminate()
                            print(f"已关闭之前的进程: PID {proc.info['pid']}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except ImportError:
        # 如果没有psutil，尝试使用系统命令
        try:
            if sys.platform.startswith('win'):
                subprocess.run(['taskkill', '/f', '/im', 'pyBranchCheck.exe'], 
                             capture_output=True, check=False)
        except Exception:
            pass
    except Exception as e:
        print(f"关闭之前进程时出错: {e}")

def ensure_config_file():
    """确保当前目录存在config.json文件"""
    current_dir = os.getcwd()
    config_file = os.path.join(current_dir, 'config.json')
    
    if not os.path.exists(config_file):
        # 从程序内置配置复制到当前目录
        try:
            internal_config = load_config()
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(internal_config, f, ensure_ascii=False, indent=2)
            print(f"✅ 已在当前目录生成配置文件: {config_file}")
        except Exception as e:
            print(f"❌ 生成配置文件失败: {e}")
    else:
        print(f"✅ 配置文件已存在: {config_file}")

if __name__ == '__main__':
    # 检查是否为打包后的exe运行
    is_exe = getattr(sys, 'frozen', False)
    
    if is_exe:
        try:
            # 打包后的exe模式
            print("pyBranchCheck 正在启动...")
            print("服务器启动后将自动打开浏览器")
            print("如果浏览器没有自动打开，请手动访问: http://localhost:5000")
            print("关闭此窗口将停止服务")
            print("-" * 50)
            
            # 初始化Git环境
            try:
                setup_git_environment()
                print("✅ Git环境初始化成功")
                
                # 显示Git版本信息
                result = subprocess.run(['git', '--version'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    print(f"Git版本: {result.stdout.strip()}")
            except Exception as e:
                print("\n❌ 错误: Git环境初始化失败")
                print("\n解决方案:")
                print("1. 请从以下地址下载并安装Git:")
                print("   https://git-scm.com/download/windows")
                print("2. 安装时请确保勾选'Add Git to PATH'选项")
                print("3. 安装完成后重启电脑")
                print("4. 重新运行本程序")
                print("\n详细错误信息:", str(e))
                print("\n按任意键退出...")
                input()
                sys.exit(1)
            
            # 在新线程中打开浏览器
            threading.Thread(target=open_browser, daemon=True).start()
            
            # 生产模式运行
            app.run(debug=False, host='127.0.0.1', port=5000)
            
        except KeyboardInterrupt:
            print("\n程序已停止")
        except Exception as e:
            print(f"\n❌ 程序启动失败: {str(e)}")
            print("\n可能的解决方案:")
            print("1. 确保已安装Git")
            print("2. 确保端口5000未被占用")
            print("3. 以管理员身份运行程序")
            print("\n按任意键退出...")
            input()
            sys.exit(1)
    else:
        # 开发模式 - 也需要初始化Git环境
        try:
            setup_git_environment()
            print("Git环境初始化成功")
        except Exception as e:
            print(f"警告: Git环境初始化失败 - {e}")
            print("某些功能可能无法正常工作")
        
        app.run(debug=True, host='0.0.0.0', port=5000)