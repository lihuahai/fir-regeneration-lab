# 冷杉更新研究室（Netlify 在线版）

正式网址：https://fir-regeneration-lab.netlify.app

已通过 Netlify Drop 发布，无需 Python 服务器。计算引擎通过 Pyodide 在每位访客的浏览器中运行，上传的研究数据不会发送到分析服务器。首次访问需要下载约 42 MB 的分析组件；组件均随站点托管，不依赖第三方 CDN。

## 使用方法

1. 打开正式网址，等待首次组件加载。
2. 点击“导入数据”选择 Excel / CSV；修改电脑上的文件并保存后，再次导入即可重算。
3. 也可在“数据与变量”修改数值、增加样方或新增变量，结果自动更新。
4. 用“导出分析报告”和“导出原始数据”保存结果。各访客的工作副本互不覆盖；刷新同一标签页可恢复，关闭标签页后请勿依赖它长期保存。

原版 Excel 为左右双表，新环境变量可加在右侧环境表末尾，并按样方编号对应。普通表为一行一个样方，首列为“样方编号”。数值型环境变量可进入关联和模型分析。支持最多 300 个样方、40 列、5 MB 文件；首个工作表不超过 1000 行、80 列。模型最多同时选择 3 个环境因子。

分享网址只分享网站，不会携带你当前编辑的数据。分享结果请导出报告，分享数据请导出 CSV。电脑关机不影响公开网站访问。

公开示例已获授权：48 个样方、12 个大样地、638 株。I 级 0<H≤20 cm，II 级 20<H≤40 cm，III 级 H>40 cm。面积未知，以株/样方描述；同一前缀为同一大样地，组间置换和相关分析考虑该结构。所有结果用于探索，不作因果或存活率推断。

## 更新网站

源码仓库：https://github.com/lihuahai/fir-regeneration-lab

当前为手动部署，GitHub 推送不会自动更新 Netlify。更改代码或默认示例后，重新构建，把 site 文件夹内全部文件打成 ZIP（ZIP 根目录直接为 index.html），在 Netlify 的 fir-regeneration-lab 项目概览中选择文件上传。不要创建另一项目。

已生成的部署包：outputs/冷杉网站_Netlify部署包.zip。

重新构建（Node.js ≥22.13，Python 用于准备文件，不参与在线运算）：

```sh
npm ci
python3 -m pip download --no-deps openpyxl==3.1.5 et-xmlfile==2.0.0 -d public/python-runtime
python3 scripts/prepare-browser-runtime.py
npm run build:netlify
python3 scripts/package-netlify.py
```

已有 public/python-runtime 中校验匹配的依赖会复用。Pyodide 固定为 314.0.7，下载的统计包按锁文件 SHA256 校验。前端、Worker、统计引擎及公开示例均在 site 中。

修改所有访客默认看到的示例：运行 `.venv/bin/python scripts/update-example.py 新数据.xlsx`，再执行准备组件、构建和打包步骤，然后重新上传 Netlify。访客可点击“载入示例数据”载入新版本。

原有桌面模式仍可使用“启动冷杉分析.command”，跟随本机 Excel 保存变化。Dockerfile、render.yaml、Flask 等是保留的服务器部署方案，当前 Netlify 不使用它们。
