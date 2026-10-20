# VEYRA

**[English](#english) · [中文](#中文)**

---

## English

VEYRA connects cattle identification, indicative valuation, camera health monitoring, and insurance through one **Digital Livestock Passport**. A farm manager can follow one animal through the whole journey:

1. Enroll the animal from a guided phone video. Its muzzle print becomes its ID.
2. Keep a passport with its evidence, estimates, and an indicative value.
3. Push the enrolled herd to the pen cameras. A muzzle scan in the camera's scan zone tells the CCTV which track is which animal.
4. Get movement alerts from the cameras.
5. Get a sandbox insurance policy through the in-app **VEYRA agent**.
6. File a claim. A death claim needs a muzzle re-scan that matches the enrolled animal.

Every step is tied to the same animal ID and recorded in an audit trail. Nothing financial happens without a manager's explicit approval: the agent prepares, a person stamps.

This is a hackathon prototype. Every insurer, payment, and claim is a sandbox. Screens label every output `live`, `prototype`, `simulated`, or `documented`.

### What's in the app

| Screen | Route | What it does |
| --- | --- | --- |
| Pitch page | `/` | The story, proof figures with their limits, and **Open the live demo** |
| Herd | `/herd` | Every animal with its identity, weight, monitoring, and coverage status |
| Enroll | `/enroll` | Guided camera capture with a live muzzle-quality meter, or an uploaded video. Frame picks, a muzzle match against the farm, and an honest review list |
| Passport | `/animals/:id` | Identity evidence, estimates, valuation, documents, coverage, location, and camera gallery sync, with the passbook beside them |
| Monitor | `/monitor` | Camera replays with tracks, the calibrated scan zone, the pen map, and alerts. **Pen A camera footage** runs a real tracker on barn video, and the real muzzle matcher decides the scan-zone identity |
| VEYRA agent | `/agent?animal=…&intent=find_insurance\|file_claim\|track_claim` | Asks only for missing facts, compares plans, prepares applications, payments, and claim submissions, and tracks insurer-reported status |
| Approvals | `/approvals` | The manager reviews the exact payload and evidence, then approves and stamps, or declines |
| Claims | `/claims` | Incidents, evidence checklists, vet findings, the farmer declaration, and the muzzle identity check |
| Audit | `/audit` | Agent proposals, human decisions, and provider results as separate rows |
| Ask | top bar | Natural-language questions ("Where was Sari last seen?") answered from the records |

### Repository map

| Path | What it holds |
| --- | --- |
| `services/api/` | FastAPI backend on SQLite: passport and passbook, enrollment, valuation, insurance, agent wallet (approvals and sandbox execution), the VEYRA agent, monitoring replays and alerts, camera galleries, assistant, claims and identity checks, audit. See `services/api/README.md`. |
| `apps/web/` | React 19 + Vite + Tailwind 4 web app: the pitch page and the app. |
| `demo/` | `fixtures/` (herd, policies, enrollment samples), `scenarios/` (camera replays), `media/veo/` (the phone enrollment video and the Pen A barn footage), and `uploads/` (the files to upload during the demo, described in its README). |
| `ml/` | Training and evaluation for the muzzle matcher, weight, and tracking. The API calls it only through `services/api/adapters/perception.py`. |
| `shared/schemas/openapi.json` | The API contract. The web app generates its types from it. |
| `docs/technical-document/` | The technical paper (PDF and LaTeX source). |

### How to run

There are two ways to run VEYRA. Docker is the quickest: one command builds and serves everything. Development mode runs the backend and the web app separately, with hot reload, for working on the code.

#### Option 1: Docker (recommended)

You need Docker Desktop and Git LFS.

1. Get the code and the large files (models, videos, images):

   ```bash
   git clone https://github.com/ShibainuID/Veyra.git
   cd Veyra
   git lfs pull
   ```

2. Optional: turn on the language model. Copy `.env.example` to `.env` and set `OPENAI_API_KEY`. Without a key, every explanation is a labeled offline template and the rest of the app works the same.
3. Build and start:

   ```bash
   docker compose up --build
   ```

4. Open http://localhost:8000 for the pitch page, or http://localhost:8000/herd for the app.

Stop it with `Ctrl+C`, or with `docker compose down` from another terminal.

- **Full ML path:** `VEYRA_PERCEPTION_BUILD=true docker compose up --build` adds torch, Ultralytics, and OpenCLIP, so real video frame picks and the weight model run. The image grows by several GB. The default image already includes the real muzzle matcher (ONNX).
- **Another port:** `VEYRA_PORT=8090 docker compose up`.
- **Data:** the database and media live in the `veyra-data` volume. `docker compose down -v` deletes them. The Demo button in the app resets them without a restart.
- **After changing `.env`:** run `docker compose up -d --force-recreate`.
- **Without compose:** `docker build -t veyra .`, then `docker run -p 8000:8000 -v veyra-data:/data veyra`.

The container runs one uvicorn worker on purpose, because background jobs and camera replays live in the API process.

#### Option 2: Development mode

You need Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22 with pnpm 10, and Git LFS (`git lfs pull` after cloning). The commands are the same on Windows (PowerShell or Git Bash) and macOS.

Backend, in terminal 1:

```bash
cd services/api
uv sync                                  # add --extra perception for the full ML path
uv run uvicorn main:app --port 8000      # http://localhost:8000/api/v1/health
```

Web app, in terminal 2:

```bash
pnpm -C apps/web install
pnpm -C apps/web dev                     # http://localhost:5173, proxies /api to port 8000
```

Open http://localhost:5173. The backend reads the root `.env` too, so the same `OPENAI_API_KEY` works here. The database is created and seeded on first start under `services/api/.data/`.

If port 8000 is taken, start the API on another port and point the web app at it with `VEYRA_API_TARGET=http://127.0.0.1:8010 pnpm -C apps/web dev`. In PowerShell, use `$env:VEYRA_API_TARGET="http://127.0.0.1:8010"; pnpm -C apps/web dev`.

### Demo walkthrough

From the landing page through every feature, in order. The files to upload are in `demo/uploads/`:

1. Enroll Sari from `video_hp.mp4`.
2. Confirm a valuation and upload the ownership PDF.
3. Push the herd to the cameras and watch the Pen A footage identify her.
4. Run the reduced-movement replay.
5. Insure her with the agent.
6. File a death claim.
7. Re-scan the muzzle. `09_hp_muzzle.png` should match and `05_muzzle_closeup.jpg` should not.
8. Check the audit trail.

### Execution evidence

VEYRA is not on-chain, so its evidence is sandbox operation logs. **The report is [`docs/evidence/SUMMARY.md`](docs/evidence/SUMMARY.md).** It lists every operation of a full run in order, with its actor, result, and sandbox receipt, and the controls the run shows: the agent prepares and a person approves, approval binds the exact payload, payment alone does not activate cover, and a wrong-cow muzzle blocks a claim.

The raw logs sit next to it in `docs/evidence/`: the audit events, the wallet ledger, the policies, and the claims. Running the demo walkthrough above produces the same records.

### Demo accounts

There is no login. The role switcher in the top bar (in **More** on a phone) changes the demo bearer token:

| Role | Token | Can do |
| --- | --- | --- |
| Manager (W. Santoso) | `demo-manager` | Everything, including approving and declining actions and resetting the demo |
| Operator (A. Pratama) | `demo-operator` | Enroll, start replays, review tracks and alerts, record incidents, prepare actions. Cannot approve |
| Vet (dr. R. Lestari) | `demo-vet` | Add professional findings to incidents. No payment authority |
| Assessor | `demo-assessor` | Read sandbox submissions (API only) |

### Demo reset

In the app, as Manager: open the flask button in the top bar (**Demo**), pick **Fresh herd** or **After enrollment**, and confirm. From a terminal:

```bash
curl -X POST "http://localhost:8000/api/v1/demo/reset?scenario=fresh" -H "Authorization: Bearer demo-manager"
```

- `fresh` seeds five cattle.
- `post-enrollment` also seeds Sari (`animal-demo-001`) with a confirmed valuation.

The sandbox provider switches are at `PUT /api/v1/demo/settings`: the payment can succeed, fail, or time out, and the insurer can confirm or withhold activation.

### Configuration

Every variable is optional. The defaults run the demo. Copy `.env.example` to `.env` at the repo root. Both `uv run uvicorn main:app` and `docker compose` read it, and a variable already set in the shell wins.

| Variable | Default | Effect |
| --- | --- | --- |
| `VEYRA_DATA_DIR` | `services/api/.data` | Where the SQLite database and uploaded media live |
| `VEYRA_DATABASE_URL` | `sqlite:///<data dir>/veyra.db` | Database URL (SQLite only) |
| `VEYRA_MEDIA_SECRET` | random per process | Signs media URLs. Set it so links survive a restart |
| `VEYRA_SERVICE_TOKEN` | `demo-worker-token` | Token for the internal camera and worker endpoints (`X-Service-Token`) |
| `VEYRA_SYNC_JOBS` | `false` | Run background jobs inline (tests use this) |
| `VEYRA_REPLAY_SPEED` | `10` | Camera replay speed multiplier. `0` ingests a whole replay at once |
| `VEYRA_PERCEPTION_MODE` | `auto` | `auto` uses each installed ML capability, `prototype` asks for all of them and logs what's missing, `fixture` uses labeled fixtures only |
| `VEYRA_LLM_MODE` | `auto` | `auto` goes live when the provider's key is set, `live` always tries, `offline` uses templates and the offline parser |
| `VEYRA_LLM_PROVIDER` | `openai` | `openai` or `anthropic` |
| `VEYRA_LLM_MODEL` | `gpt-6-luna` | Model for explanations and question parsing (`claude-opus-5-5` with `anthropic`) |
| `VEYRA_DEMO_MODE` | `true` | Exposes `/api/v1/demo/*` (reset, replays, sandbox switches, demo footage) |
| `VEYRA_YOLO_WEIGHTS` | `yolov8x-seg.pt` | Segmentation weights for the weight step: an Ultralytics name or a local path |
| `OPENAI_API_KEY` | unset | Enables the live model with the `openai` provider |
| `ANTHROPIC_API_KEY` | unset | The same for the `anthropic` provider |
| `VEYRA_API_TARGET` (web) | `http://127.0.0.1:8000` | Where the Vite dev and preview servers proxy `/api` |

### Tests

```bash
cd services/api && uv run pytest -q          # backend
pnpm -C apps/web typecheck
pnpm -C apps/web test
pnpm -C apps/web build
```

- **Backend (pytest, about 550 tests).** `tests/domain/` checks the rules on their own: eligibility, valuation, evidence labels, movement alerts, identity handoff, and the database transaction guards. `tests/integration/` drives the real API end to end: enrollment, the agent wallet (approval, idempotent execution, ledger, insurer activation), claims and muzzle identity checks, camera replays, the VEYRA agent, and role scoping. `test_critical_verification.py` holds one test for each of the ten critical checks.
- **Web (Vitest, about 135 tests).** Screens and components: the approve-and-stamp flow, enrollment steps, monitor overlays, the agent cards, and the labels each one shows.
- **Typecheck and build** confirm that the web app compiles against the generated API types.

The tests need no API key and no network. They use the offline language-model fallback, and stand-in models where a real one would be slow.

### Regenerating the API contract

After changing a route or schema in `services/api`:

```bash
cd services/api
uv run python -c "import json,main; open('../../shared/schemas/openapi.json','w').write(json.dumps(main.app.openapi(), indent=2))"
cd ../..
pnpm -C apps/web gen:api                     # rewrites apps/web/src/lib/api-types.ts
```

### Limits

- **Sandbox only.** No real money moves, no policy is bound, and no claim is filed. The wallet is a sandbox ledger, and the insurer (Sandbox Mutual) and the payment provider are simulated.
- **Fixture data.** The policies, the price (5.20 USD/kg), the herd, and the synthetic camera replays are fixtures.
- **Demo footage.** The videos in `demo/media/veo/` were made with Google Veo for this prototype, and `VEO_PROMPTS.md` has the prompts. The tracker and the muzzle matcher run on them for real.
- **No diagnoses or payout promises.** Alerts are observations for inspection, not diagnoses. An indicative value is not an insurer-agreed value or a payout.
- **Prototype models.** The muzzle matcher, weight estimate, and tracker make no production accuracy claim. Weight needs the scale marker in view, and age comes from a fixture.

---

## 中文

VEYRA 通过一本**数字牲畜护照**，把牛只身份识别、参考估值、摄像头健康监测和保险连在一起。养殖场管理者可以跟着一头牛走完全程：

1. 用引导式手机视频为牛只登记，鼻纹就是它的身份。
2. 拥有一本护照，记录证据、估算和参考价值。
3. 把已登记的牛群推送到圈舍摄像头。牛只在扫描区内扫描鼻纹后，CCTV 就知道哪条轨迹是哪头牛。
4. 接收摄像头发出的活动量告警。
5. 通过应用内的 **VEYRA 智能体**办理沙盒保险。
6. 提交理赔。死亡理赔必须重新扫描鼻纹，并与登记的牛只匹配。

每一步都关联到同一个牛只编号，并记录在审计日志中。任何涉及资金的操作都必须由管理者明确批准：智能体负责准备，由人来盖章确认。

这是一个黑客松原型。所有保险公司、支付和理赔都是沙盒环境。界面上每个结果都标注为 `live`（实时）、`prototype`（原型模型）、`simulated`（模拟）或 `documented`（有记录）。

### 应用功能

| 页面 | 路由 | 功能 |
| --- | --- | --- |
| 宣传页 | `/` | 产品故事、附带局限说明的验证数据，以及 **Open the live demo**（打开在线演示） |
| 牛群 | `/herd` | 每头牛的身份、体重、监测和保障状态 |
| 登记 | `/enroll` | 带实时鼻纹清晰度提示的引导拍摄，或上传视频。自动选帧，与本场牛只比对鼻纹，并如实列出待复核项 |
| 护照 | `/animals/:id` | 身份证据、估算、估值、文件、保障、位置和摄像头图库同步，旁边是存折式记录 |
| 监控 | `/monitor` | 带轨迹的摄像头回放、已校准的扫描区、圈舍地图和告警。**Pen A camera footage**（A 圈摄像头画面）在牛舍视频上运行真实的跟踪器，扫描区内的身份由真实的鼻纹匹配器判定 |
| VEYRA 智能体 | `/agent?animal=…&intent=find_insurance\|file_claim\|track_claim` | 只询问缺失的信息，比较保险方案，准备投保申请、付款和理赔提交，并跟踪保险公司反馈的状态 |
| 审批 | `/approvals` | 管理者核对确切的提交内容和证据，然后批准并盖章，或拒绝 |
| 理赔 | `/claims` | 事故、证据清单、兽医意见、养殖户声明和鼻纹身份核验 |
| 审计 | `/audit` | 智能体提议、人工决定和服务方结果分行记录 |
| 提问 | 顶栏 | 用自然语言提问（如"Sari 最后出现在哪里？"），答案来自记录 |

### 仓库结构

| 路径 | 内容 |
| --- | --- |
| `services/api/` | 基于 SQLite 的 FastAPI 后端：护照与存折记录、登记、估值、保险、智能体钱包（审批与沙盒执行）、VEYRA 智能体、监控回放与告警、摄像头图库、助手、理赔与身份核验、审计。见 `services/api/README.md`。 |
| `apps/web/` | React 19 + Vite + Tailwind 4 网页应用：宣传页和应用本身。 |
| `demo/` | `fixtures/`（牛群、保单、登记样例）、`scenarios/`（摄像头回放）、`media/veo/`（手机登记视频和 A 圈牛舍画面）、`uploads/`（演示时要上传的文件，见其 README）。 |
| `ml/` | 鼻纹匹配、体重和跟踪的训练与评估。API 只通过 `services/api/adapters/perception.py` 调用。 |
| `shared/schemas/openapi.json` | API 契约，网页应用据此生成类型。 |
| `docs/technical-document/` | 技术文档（PDF 与 LaTeX 源文件）。 |

### 如何运行

有两种运行方式。Docker 最快，一条命令即可构建并启动全部内容。开发模式分别运行后端和网页应用，支持热更新，适合修改代码。

#### 方式一：Docker（推荐）

需要 Docker Desktop 和 Git LFS。

1. 获取代码和大文件（模型、视频、图片）：

   ```bash
   git clone https://github.com/ShibainuID/Veyra.git
   cd Veyra
   git lfs pull
   ```

2. 可选：启用语言模型。把 `.env.example` 复制为 `.env`，并填入 `OPENAI_API_KEY`。没有密钥时，所有解释都是带标注的离线模板，其余功能不受影响。
3. 构建并启动：

   ```bash
   docker compose up --build
   ```

4. 打开 http://localhost:8000 查看宣传页，或打开 http://localhost:8000/herd 进入应用。

按 `Ctrl+C` 停止，或在另一个终端运行 `docker compose down`。

- **完整机器学习链路：** `VEYRA_PERCEPTION_BUILD=true docker compose up --build` 会加入 torch、Ultralytics 和 OpenCLIP，运行真实的视频选帧和体重模型，镜像会增大数 GB。默认镜像已包含真实的鼻纹匹配器（ONNX）。
- **其他端口：** `VEYRA_PORT=8090 docker compose up`。
- **数据：** 数据库和媒体文件存放在 `veyra-data` 卷中。`docker compose down -v` 会删除它们。应用中的 Demo 按钮可在不重启的情况下重置。
- **修改 `.env` 后：** 运行 `docker compose up -d --force-recreate`。
- **不使用 compose：** 先 `docker build -t veyra .`，再 `docker run -p 8000:8000 -v veyra-data:/data veyra`。

容器特意只运行一个 uvicorn 进程，因为后台任务和摄像头回放都在 API 进程中。

#### 方式二：开发模式

需要 Python 3.12 与 [uv](https://docs.astral.sh/uv/)、Node 22 与 pnpm 10，以及 Git LFS（克隆后运行 `git lfs pull`）。Windows（PowerShell 或 Git Bash）和 macOS 上命令相同。

后端，在终端 1 中运行：

```bash
cd services/api
uv sync                                  # 加 --extra perception 启用完整机器学习链路
uv run uvicorn main:app --port 8000      # http://localhost:8000/api/v1/health
```

网页应用，在终端 2 中运行：

```bash
pnpm -C apps/web install
pnpm -C apps/web dev                     # http://localhost:5173，/api 代理到 8000 端口
```

打开 http://localhost:5173。后端同样读取根目录的 `.env`，所以同一个 `OPENAI_API_KEY` 在这里也有效。首次启动时会在 `services/api/.data/` 下创建数据库并写入演示数据。

如果 8000 端口被占用，可在其他端口启动 API，并用 `VEYRA_API_TARGET=http://127.0.0.1:8010 pnpm -C apps/web dev` 让网页指向它。PowerShell 下为 `$env:VEYRA_API_TARGET="http://127.0.0.1:8010"; pnpm -C apps/web dev`。

### 演示流程

从宣传页开始，按顺序体验每个功能。要上传的文件在 `demo/uploads/` 中：

1. 用 `video_hp.mp4` 登记 Sari。
2. 确认估值并上传所有权 PDF。
3. 把牛群推送到摄像头，在 A 圈画面中看到她被识别。
4. 运行活动量下降回放。
5. 通过智能体为她投保。
6. 提交死亡理赔。
7. 重新扫描鼻纹：`09_hp_muzzle.png` 应匹配，`05_muzzle_closeup.jpg` 不应匹配。
8. 查看审计日志。

### 执行证据

VEYRA 不涉及链上操作，因此执行证据是沙盒操作日志。**报告见 [`docs/evidence/SUMMARY.md`](docs/evidence/SUMMARY.md)。** 它按顺序列出一次完整运行中的每个操作，包括执行者、结果和沙盒回执，以及运行中体现的控制：智能体准备、由人批准，批准绑定确切的提交内容，仅付款不会使保障生效，鼻纹不符时理赔会被拦截。

原始日志在同一目录 `docs/evidence/` 中：审计事件、钱包账本、保单和理赔。按上面的演示流程操作即可生成相同的记录。

### 演示账号

无需登录。顶栏的角色切换（手机上在 **More** 中）会更换演示用的 bearer token：

| 角色 | Token | 权限 |
| --- | --- | --- |
| 管理者（W. Santoso） | `demo-manager` | 全部权限，包括批准、拒绝操作和重置演示 |
| 操作员（A. Pratama） | `demo-operator` | 登记、启动回放、复核轨迹和告警、记录事故、准备操作，不能批准 |
| 兽医（dr. R. Lestari） | `demo-vet` | 为事故添加专业意见，无付款权限 |
| 理赔评估员 | `demo-assessor` | 查看沙盒提交（仅 API） |

### 重置演示

在应用中以管理者身份打开顶栏的烧瓶按钮（**Demo**），选择 **Fresh herd** 或 **After enrollment** 并确认。也可在终端执行：

```bash
curl -X POST "http://localhost:8000/api/v1/demo/reset?scenario=fresh" -H "Authorization: Bearer demo-manager"
```

- `fresh` 写入五头牛。
- `post-enrollment` 另外写入已确认估值的 Sari（`animal-demo-001`）。

沙盒服务开关在 `PUT /api/v1/demo/settings`：付款可设为成功、失败或超时，保险公司可确认或暂缓生效。

### 配置

所有变量都是可选的，默认值即可运行演示。把 `.env.example` 复制为根目录的 `.env`。`uv run uvicorn main:app` 和 `docker compose` 都会读取它，shell 中已设置的变量优先。

| 变量 | 默认值 | 作用 |
| --- | --- | --- |
| `VEYRA_DATA_DIR` | `services/api/.data` | SQLite 数据库和上传媒体的存放位置 |
| `VEYRA_DATABASE_URL` | `sqlite:///<data dir>/veyra.db` | 数据库地址（仅支持 SQLite） |
| `VEYRA_MEDIA_SECRET` | 每个进程随机 | 签名媒体链接，设置后链接在重启后仍有效 |
| `VEYRA_SERVICE_TOKEN` | `demo-worker-token` | 内部摄像头和后台任务接口的令牌（`X-Service-Token`） |
| `VEYRA_SYNC_JOBS` | `false` | 同步执行后台任务（测试时使用） |
| `VEYRA_REPLAY_SPEED` | `10` | 摄像头回放倍速，`0` 表示一次性导入整段回放 |
| `VEYRA_PERCEPTION_MODE` | `auto` | `auto` 使用已安装的各项机器学习能力，`prototype` 要求全部能力并记录缺失项，`fixture` 只用带标注的固定数据 |
| `VEYRA_LLM_MODE` | `auto` | `auto` 在设置了服务方密钥时启用实时模型，`live` 始终尝试，`offline` 使用模板和离线解析器 |
| `VEYRA_LLM_PROVIDER` | `openai` | `openai` 或 `anthropic` |
| `VEYRA_LLM_MODEL` | `gpt-6-luna` | 用于解释和问题解析的模型（`anthropic` 时为 `claude-opus-5-5`） |
| `VEYRA_DEMO_MODE` | `true` | 开放 `/api/v1/demo/*`（重置、回放、沙盒开关、演示视频） |
| `VEYRA_YOLO_WEIGHTS` | `yolov8x-seg.pt` | 体重估算使用的分割模型权重：Ultralytics 名称或本地路径 |
| `OPENAI_API_KEY` | 未设置 | 为 `openai` 服务方启用实时模型 |
| `ANTHROPIC_API_KEY` | 未设置 | 为 `anthropic` 服务方启用实时模型 |
| `VEYRA_API_TARGET`（网页） | `http://127.0.0.1:8000` | Vite 开发和预览服务器代理 `/api` 的目标地址 |

### 测试

```bash
cd services/api && uv run pytest -q          # 后端
pnpm -C apps/web typecheck
pnpm -C apps/web test
pnpm -C apps/web build
```

- **后端（pytest，约 550 个测试）。** `tests/domain/` 单独检查各项规则：资格判断、估值、证据标注、活动量告警、身份交接和数据库事务保护。`tests/integration/` 通过真实 API 端到端运行：登记、智能体钱包（审批、幂等执行、账本、保险公司生效确认）、理赔与鼻纹身份核验、摄像头回放、VEYRA 智能体和角色权限。`test_critical_verification.py` 为十项关键检查各写了一个测试。
- **网页（Vitest，约 135 个测试）。** 覆盖页面和组件：批准盖章流程、登记步骤、监控叠加层、智能体卡片，以及它们显示的标注。
- **类型检查和构建** 确认网页应用能基于生成的 API 类型正确编译。

测试不需要 API 密钥，也不需要网络。语言模型使用离线回退，耗时的真实模型用替身代替。

### 重新生成 API 契约

修改 `services/api` 中的路由或数据结构后：

```bash
cd services/api
uv run python -c "import json,main; open('../../shared/schemas/openapi.json','w').write(json.dumps(main.app.openapi(), indent=2))"
cd ../..
pnpm -C apps/web gen:api                     # 重写 apps/web/src/lib/api-types.ts
```

### 局限

- **仅限沙盒。** 不会发生真实资金往来，不会签发真实保单，也不会提交真实理赔。钱包是沙盒账本，保险公司（Sandbox Mutual）和支付服务方均为模拟。
- **固定数据。** 保单、价格（5.20 美元/公斤）、牛群和合成的摄像头回放都是固定的演示数据。
- **演示视频。** `demo/media/veo/` 中的视频是为本原型用 Google Veo 制作的，提示词见 `VEO_PROMPTS.md`。跟踪器和鼻纹匹配器在这些视频上真实运行。
- **不作诊断，不承诺赔付。** 告警只是供人工检查的观察结果，并非诊断。参考价值不是保险公司认可的价值，也不是赔付金额。
- **原型模型。** 鼻纹匹配、体重估算和跟踪器均不宣称达到生产级准确率。体重估算需要画面中有比例标记，年龄来自固定数据。
