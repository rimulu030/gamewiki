# 如何测试他人提交的 PR（来自 Fork）

当有人从自己的 fork（如 https://github.com/Jeeeeeeeeeja/gamewiki）提 PR 到你的仓库时，可以按下面步骤在本地拉取并测试。

## 1. 添加 PR 作者的远程仓库

在项目根目录执行：

```bash
git remote add jee https://github.com/Jeeeeeeeeeja/gamewiki.git
```

（`jee` 是远程的简短名称，可改成任意名字，如 `pr-author`。）

## 2. 拉取对方仓库的提交

```bash
git fetch jee
```

## 3. 查看对方有哪些分支

```bash
git branch -r
```

会看到类似 `jee/master`、`jee/某个功能分支`。PR 通常会在某个具体分支上（在 GitHub PR 页面会写明「head」分支名）。

## 4. 用对方分支创建本地测试分支

假设 PR 来自对方仓库的 `master` 分支：

```bash
git checkout -b test-pr-jee master
git pull jee master
```

如果 PR 来自对方仓库的**其他分支**（例如 `fix-xxx`），则：

```bash
git checkout -b test-pr-jee jee/fix-xxx
```

（把 `fix-xxx` 换成 PR 页面上显示的 head 分支名。）

## 5. 安装依赖并运行项目

```bash
pip install -r requirements.txt
python -m src.game_wiki_tooltip
```

按项目需要配置环境变量（如 `GEMINI_API_KEY`），然后做功能/回归测试。

## 6. 测试完成后切回主分支

```bash
git checkout master
```

若不再需要该远程，可删除：

```bash
git remote remove jee
```

---

## 快速命令汇总（PR 在对方 master 时）

```bash
git remote add jee https://github.com/Jeeeeeeeeeja/gamewiki.git
git fetch jee
git checkout -b test-pr-jee jee/master
pip install -r requirements.txt
python -m src.game_wiki_tooltip
```

测试完后：

```bash
git checkout master
git branch -d test-pr-jee
```

---

**安全审查**：对 PR 的 diff 做安全审查（危险模式、恶意注入等）可参考 [PR_SECURITY_REVIEW.md](PR_SECURITY_REVIEW.md)。针对 Jeeeeeeeeeja 的俄语支持 PR 已有一份审查结论：未发现危险行为。
