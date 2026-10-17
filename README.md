# 冷杉更新研究室

用于探索郁闭度、环境因子与冷杉更新的关系。支持 Excel / CSV 导入、修改样方数据、添加变量、自动重算，以及导出分析报告和工作数据。

公开示例包含 48 个样方、12 个大样地、638 株更新个体。高度级标准为 I：0 < H ≤ 20 cm，II：20 < H ≤ 40 cm，III：H > 40 cm。原表左右两块数据按样方编号合并。统计控制大样地内相关性；面积未知时仅比较株/样方。结果用于探索，不作因果或存活率推断。

## 推荐部署：Render Free

项目已包含 `Dockerfile` 和 `render.yaml`，可以创建一个完整的在线网站，不需要自己购买服务器或域名。部署成功后获得 `https://你的服务名.onrender.com` 地址；实际地址以 Render 面板为准。

1. 注册或登录 [GitHub](https://github.com/signup)，创建仓库 `fir-regeneration-lab`。仓库可为 Public；示例数据已获授权公开。无需选择 README 模板。
2. 将部署包解压后，上传文件夹**里面的文件和子文件夹**到仓库根目录；根目录应直接看见 `Dockerfile`、`render.yaml`、`site` 和 `analysis`。不要只上传 ZIP，也不要再包一层目录。
3. 注册或登录 [Render](https://dashboard.render.com/register)，可选择使用 GitHub 登录。授权连接刚建的仓库。
4. 在 Render 选择 **New → Blueprint**，选择上述仓库；确认只创建一个 **Free** Web Service（Singapore 区域），然后部署。配置已写好，无需手填启动命令或环境变量。
5. 等待状态显示 **Live**，打开面板提供的 `onrender.com` 地址。首次验证应看到 48 个样方、638 株，导入数据后可以重新计算。
6. 将这个 HTTPS 地址发给他人即可。电脑关机不影响云端服务。

若通过 **New → Web Service** 创建，请选择 Docker、Free、Singapore，健康检查路径设为 `/api/health`，保留 Dockerfile 的默认启动命令。不要选择 Static Site，因为统计计算需要 Python 后端。

免费实例闲置 15 分钟后会休眠，再次访问通常需要约一分钟唤醒。适合小范围研究演示；是否升级在后续根据访问速度与用量决定。暂不需要数据库、持久磁盘或付费实例。免费资源仍有每月用量上限。

官方依据：[免费实例说明](https://render.com/docs/free)、[Blueprint 配置](https://render.com/docs/blueprint-spec)、[Docker 部署](https://render.com/docs/docker)。

## 数据怎么更新

- 每位访客首次打开，看到仓库中的公开示例。
- 点击“导入数据”上传 `.xlsx` / `.csv`。修改电脑上的 Excel 并保存后，需要再次导入；云端网站不能自动读取访客电脑里的文件。
- 可在“数据与变量”中直接改值、增加样方或变量，结果自动重新计算。
- 双表原版式：新环境变量放在右侧环境表末尾，第一行写变量名，数据与右侧样方编号对应。普通表则一行一个样方，首列为“样方编号”。新增文本列默认不参与数值分析。
- 上传内容发送到服务器内存解析和计算；应用不把上传文件或分析结果写入服务器持久存储。当前数据和设置保存在当前标签页的 sessionStorage；同一标签页刷新可恢复，关闭后请勿依赖它长期留存。
- 每位访客的工作副本互不覆盖。复制网站地址不会携带你当前编辑的数据；分享当前结果请导出报告，分享当前数据请导出 CSV。
- 在线版支持最多 300 个样方、40 个变量列、5 MB 文件。首个工作表的原版式应在 1,000 行、80 列以内。模型同时最多选择 3 个环境因子。
- 改变所有访客默认看到的示例：在项目目录运行 `.venv/bin/python scripts/update-example.py 你的新数据.xlsx` 生成 `analysis/example.json`，提交到仓库，Render 自动重新部署；访客点击“载入示例数据”使用最新示例。

## 本地验证与开发

需要 Node.js ≥ 22.13 和 Python 3.12。使用普通环境安装依赖：

```sh
npm ci
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm run build:online
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/gunicorn --config gunicorn.conf.py --chdir analysis web:app
```

然后打开 `http://127.0.0.1:10000/`。这只是本机验收地址，并不是公开分享网址。

部署包已经包含经过浏览器验收的 `site/` 页面文件，Render 无需重新安装前端依赖。修改网页代码后请先运行 `npm run build:online`，再将更新后的 `site/` 提交到仓库。

也可以 `docker build -t fir-regeneration .` 后执行 `docker run --rm -p 10000:10000 fir-regeneration`。部署镜像内仅包含静态页面、统计引擎、公开示例和线上 API；不包含本机草稿、原始 Excel 路径或凭据。

```sh
npm run lint
npx tsc --noEmit
cd analysis
../.venv/bin/python -m unittest test_web -v
```

原有桌面模式继续使用“启动冷杉分析.command”，会跟随本机原始 Excel 的保存变动。线上模式与本机模式采用同一统计引擎。
