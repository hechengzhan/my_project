<script setup>
import { computed, onMounted, ref, watch } from 'vue'

const categories = ['全部', '数码', '书籍', '生活用品', '学习用品', '运动户外', '美妆服饰', '其他']
const currentTab = ref('market')
const selectedCategory = ref('全部')
const keyword = ref('')
const listings = ref([])
const loading = ref(true)
const hasMore = ref(false)
const page = ref(1)
const selectedItem = ref(null)
const showAuth = ref(false)
const authMode = ref('login')
const authForm = ref({ username: '', password: '' })
const authError = ref('')
const user = ref(JSON.parse(localStorage.getItem('lime_user') || 'null'))
const token = ref(localStorage.getItem('lime_token') || '')
const notice = ref('')
const noticeError = ref(false)
const analyzeFiles = ref([])
const analyzeNote = ref('')
const analyzing = ref(false)
const analysis = ref(null)
const analysisError = ref('')
const publishSaving = ref(false)
const myListings = ref([])
const profileLoading = ref(false)

const publishForm = computed(() => analysis.value ? {
  title: analysis.value.title,
  category: analysis.value.category,
  price_low: analysis.value.price_low,
  price_high: analysis.value.price_high,
  condition: analysis.value.condition,
  tags: analysis.value.tags?.join('、') || '',
  description: analysis.value.description,
  contact: ''
} : null)
const form = ref(null)

function flash(message, error = false) {
  notice.value = message
  noticeError.value = error
  window.setTimeout(() => { if (notice.value === message) notice.value = '' }, 3200)
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) }
  if (token.value) headers.Authorization = `Bearer ${token.value}`
  if (!(options.body instanceof FormData) && options.body) headers['Content-Type'] = 'application/json'
  const response = await fetch(path, { ...options, headers })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || '请求失败，请稍后重试')
  return data
}

async function loadListings(reset = true) {
  if (reset) { page.value = 1; loading.value = true }
  try {
    const params = new URLSearchParams({ page: String(page.value), page_size: '12' })
    if (selectedCategory.value !== '全部') params.set('category', selectedCategory.value)
    if (keyword.value.trim()) params.set('keyword', keyword.value.trim())
    const data = await api(`/api/listings?${params}`)
    listings.value = reset ? data.items : [...listings.value, ...data.items]
    hasMore.value = data.has_more
  } catch (error) {
    flash(error.message, true)
  } finally { loading.value = false }
}

function changeCategory(item) {
  selectedCategory.value = item
  loadListings()
}
let searchTimer
watch(keyword, () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => loadListings(), 320) })

function openAuth(mode = 'login') {
  authMode.value = mode
  authError.value = ''
  showAuth.value = true
}

async function submitAuth() {
  authError.value = ''
  try {
    const result = await api(`/api/auth/${authMode.value === 'login' ? 'login' : 'register'}`, { method: 'POST', body: JSON.stringify(authForm.value) })
    token.value = result.token
    user.value = result.user
    localStorage.setItem('lime_token', result.token)
    localStorage.setItem('lime_user', JSON.stringify(result.user))
    showAuth.value = false
    flash(authMode.value === 'login' ? '欢迎回来，继续逛逛吧！' : '注册成功，欢迎加入青柠校园集！')
    if (currentTab.value === 'profile') loadMine()
  } catch (error) { authError.value = error.message }
}

function logout() {
  token.value = ''; user.value = null
  localStorage.removeItem('lime_token'); localStorage.removeItem('lime_user')
  currentTab.value = 'market'; flash('已退出登录')
}

function goPublish() {
  if (!user.value) return openAuth('login')
  currentTab.value = 'publish'
  analysis.value = null; analyzeFiles.value = []; analyzeNote.value = ''; analysisError.value = ''
}

function chooseFiles(event) {
  const files = Array.from(event.target.files || [])
  if (files.length > 3) return flash('一次最多上传 3 张图片', true)
  if (files.some(file => !['image/jpeg', 'image/png', 'image/webp'].includes(file.type))) return flash('仅支持 JPG、PNG、WebP 格式', true)
  if (files.some(file => file.size > 8 * 1024 * 1024)) return flash('单张图片不能超过 8MB', true)
  analyzeFiles.value = files.map(file => ({ file, url: URL.createObjectURL(file) }))
}

async function analyze() {
  analysisError.value = ''
  if (!analyzeFiles.value.length) return analysisError.value = '请先上传至少一张商品图片'
  analyzing.value = true
  try {
    const body = new FormData()
    analyzeFiles.value.forEach(item => body.append('files', item.file))
    body.append('note', analyzeNote.value)
    analysis.value = await api('/api/ai/analyze', { method: 'POST', body })
    form.value = { ...publishForm.value }
  } catch (error) { analysisError.value = error.message } finally { analyzing.value = false }
}

async function publish() {
  if (!form.value) return
  const payload = { ...form.value, tags: form.value.tags.split(/[、,，]/).map(x => x.trim()).filter(Boolean), image_paths: analysis.value.image_paths }
  if (!payload.contact.trim()) return flash('请填写联系方法，方便同学联系你', true)
  publishSaving.value = true
  try {
    await api('/api/listings', { method: 'POST', body: JSON.stringify(payload) })
    flash('发布成功，已经展示在校园集市啦！')
    currentTab.value = 'market'
    selectedCategory.value = '全部'; keyword.value = ''
    loadListings()
  } catch (error) { flash(error.message, true) } finally { publishSaving.value = false }
}

async function openDetail(item) {
  try { selectedItem.value = await api(`/api/listings/${item.id}`) } catch (error) { flash(error.message, true) }
}

async function copyContact() {
  try { await navigator.clipboard.writeText(selectedItem.value.contact); flash('联系方式已复制') }
  catch { flash(`请手动复制：${selectedItem.value.contact}`) }
}

async function loadMine() {
  if (!user.value) return openAuth('login')
  profileLoading.value = true
  try { myListings.value = await api('/api/listings/mine') } catch (error) { flash(error.message, true) } finally { profileLoading.value = false }
}

function switchTab(tab) {
  if (tab === 'publish') return goPublish()
  if (tab === 'profile' && !user.value) return openAuth('login')
  currentTab.value = tab
  if (tab === 'profile') loadMine()
}

async function changeStatus(item, status) {
  try {
    await api(`/api/listings/${item.id}/status`, { method: 'PATCH', body: JSON.stringify({ status }) })
    flash(status === 'sold' ? '已标记为已售出' : status === 'on_sale' ? '商品已重新上架' : '商品已下架')
    loadMine(); loadListings(); if (selectedItem.value?.id === item.id) selectedItem.value.status = status
  } catch (error) { flash(error.message, true) }
}

async function deleteListing(item) {
  if (!confirm(`确定永久删除“${item.title}”吗？`)) return
  const adminDeletingOther = user.value?.is_admin && !isOwner(item)
  const endpoint = adminDeletingOther ? `/api/admin/listings/${item.id}` : `/api/listings/${item.id}`
  try { await api(endpoint, { method: 'DELETE' }); selectedItem.value = null; flash('商品已永久删除'); loadListings(); loadMine() }
  catch (error) { flash(error.message, true) }
}

function image(item) { return item.image_urls?.[0] || '' }
function date(value) { return new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric' }).format(new Date(value)) }
function isOwner(item) { return user.value && item.owner_id === user.value.id }

onMounted(loadListings)
</script>

<template>
  <div class="page-shell">
    <header class="topbar">
      <div class="container flex h-[68px] items-center justify-between gap-3">
        <button class="brand border-0 bg-transparent p-0 text-left" @click="switchTab('market')">
          <img src="/school_logo.png" alt="广州应用科技学院校徽" />
          <span>青柠校园集<small>GZASC CAMPUS MARKET</small></span>
        </button>
        <nav class="desktop-nav flex items-center gap-1">
          <button class="nav-button" :class="{ active: currentTab === 'market' }" @click="switchTab('market')">逛集市</button>
          <button class="nav-button" :class="{ active: currentTab === 'publish' }" @click="switchTab('publish')">发布闲置</button>
          <button v-if="user" class="nav-button" :class="{ active: currentTab === 'profile' }" @click="switchTab('profile')">我的小铺</button>
        </nav>
        <div class="flex items-center gap-2">
          <template v-if="user">
            <button class="hide-mobile text-sm font-bold text-[#4d764e]" @click="switchTab('profile')">{{ user.username }}<span v-if="user.is_admin" class="ml-1 text-xs text-[#d97934]">管理员</span></button>
            <button class="secondary hide-mobile !px-3 !py-2 text-xs" @click="logout">退出</button>
          </template>
          <button v-else class="secondary hide-mobile" @click="openAuth()">登录 / 注册</button>
          <button class="primary !px-3 !py-2 text-sm" @click="goPublish">＋ 发布</button>
        </div>
      </div>
    </header>

    <main class="container pb-16">
      <section v-if="currentTab === 'market'">
        <div class="hero">
          <span class="pill">🌿 广州应用科技学院 · 校园闲置交易</span>
          <h1>让每一份闲置，<br />在校园里继续闪光。</h1>
          <p>拍照上传，AI 帮你识别、估价并生成文案。校内同学面对面交易，简单、安心，也更有温度。</p>
          <button class="primary relative z-10 mt-3 bg-white !text-[#397d3e] shadow-none hover:bg-[#effbe9]" @click="goPublish">试试 AI 智能发品 →</button>
        </div>

        <div class="search-panel">
          <input v-model="keyword" class="search-input" placeholder="🔎  搜索你想找的好物，例如：耳机、教材、台灯" />
          <button class="primary" @click="loadListings()">搜索好物</button>
        </div>
        <div class="mt-8 flex items-center justify-between gap-3">
          <h2 class="section-title">校园好物集市</h2><span class="text-sm text-[#86a087]">同学们都在这里淘好物</span>
        </div>
        <div class="chips mt-4"><button v-for="category in categories" :key="category" class="chip" :class="{ active: selectedCategory === category }" @click="changeCategory(category)">{{ category }}</button></div>

        <div v-if="loading" class="grid mt-6"><div v-for="i in 8" :key="i" class="skeleton"></div></div>
        <div v-else-if="listings.length" class="grid mt-6">
          <article v-for="item in listings" :key="item.id" class="card cursor-pointer" :class="{ sold: item.status === 'sold' }" @click="openDetail(item)">
            <div class="relative"><img class="card-image" :src="image(item)" :alt="item.title" /><span v-if="item.status === 'sold'" class="status">已售出</span></div>
            <div class="p-3.5"><div class="mb-1 flex items-center justify-between gap-2 text-xs text-[#7a957b]"><span>{{ item.category }} · {{ item.condition }}</span><span>{{ date(item.created_at) }}</span></div>
              <h3 class="line-clamp-1 text-[15px] font-bold text-[#334c37]">{{ item.title }}</h3>
              <div class="mt-2 h-5 overflow-hidden"><span v-for="tag in item.tags.slice(0, 2)" :key="tag" class="tag">{{ tag }}</span></div>
              <p class="mt-2 text-[18px] font-extrabold text-[#ee7545]">¥{{ item.price_low }}<span class="text-sm"> - {{ item.price_high }}</span></p>
            </div>
          </article>
        </div>
        <div v-else class="empty mt-6"><div class="text-4xl">🍃</div><p class="mb-3 font-bold">还没有找到相关好物</p><button class="secondary" @click="selectedCategory='全部'; keyword=''; loadListings()">查看全部商品</button></div>
        <div v-if="hasMore && !loading" class="mt-7 text-center"><button class="secondary" @click="page++; loadListings(false)">加载更多好物</button></div>
      </section>

      <section v-else-if="currentTab === 'publish'" class="mx-auto mt-8 max-w-[800px]">
        <div class="mb-6"><span class="pill !bg-[#eaf7e7] !text-[#478149] !border-[#d7ebd4]">AI 智能发品助手</span><h1 class="section-title mt-3 text-3xl">三步发布你的闲置</h1><p class="mt-2 text-sm leading-6 text-[#718b73]">上传实拍图，AI 将识别物品、评估成色，并生成适合校园群分享的交易文案。</p></div>
        <div v-if="!analysis" class="card p-6 md:p-8">
          <div class="mb-5 flex items-center gap-3"><span class="step">1</span><div><h2 class="font-bold text-[#36523a]">上传商品实拍图</h2><p class="mt-1 text-sm text-[#7c967c]">支持 1 - 3 张 JPG、PNG、WebP 图片，单张不超过 8MB</p></div></div>
          <label class="dropzone block cursor-pointer"><input class="hidden" type="file" accept="image/jpeg,image/png,image/webp" multiple @change="chooseFiles" /><div class="text-3xl">📷</div><strong class="mt-2 block">点击选择图片</strong><span class="mt-1 block text-sm">建议包含整体、细节和配件照片</span></label>
          <div v-if="analyzeFiles.length" class="mt-4 grid grid-cols-3 gap-3"><img v-for="item in analyzeFiles" :key="item.url" class="preview" :src="item.url" alt="商品预览图" /></div>
          <div class="mt-5"><label class="label">补充说明（选填）</label><textarea v-model="analyzeNote" class="field min-h-24 resize-y" maxlength="300" placeholder="例如：2024 年购入，带原装充电线，轻微使用痕迹……"></textarea></div>
          <p v-if="analysisError" class="notice error mt-4">{{ analysisError }}</p>
          <button class="primary mt-5 w-full" :disabled="analyzing" @click="analyze">{{ analyzing ? 'AI 正在认真分析图片，请稍候…' : '✨ 开始 AI 识别与智能估价' }}</button>
          <p class="mt-3 text-center text-xs text-[#8aa08b]">系统会自动拦截敏感文字与疑似违规物品，请勿发布违法或不适宜商品。</p>
        </div>
        <div v-else class="card p-6 md:p-8">
          <div class="mb-6 flex items-center gap-3"><span class="step">2</span><div><h2 class="font-bold text-[#36523a]">核对 AI 生成的信息</h2><p class="mt-1 text-sm text-[#7c967c]">{{ analysis.source }}，你可在发布前自由修改全部内容。</p></div></div>
          <div class="mb-5 grid grid-cols-3 gap-3"><img v-for="url in analysis.image_paths" :key="url" class="preview" :src="url" alt="识别商品图" /></div>
          <div class="grid grid-cols-1 gap-4 md:grid-cols-2"><div><label class="label">商品标题</label><input v-model="form.title" class="field" /></div><div><label class="label">商品分类</label><select v-model="form.category" class="field"><option v-for="item in categories.slice(1)" :key="item">{{ item }}</option></select></div><div><label class="label">建议价格区间（元）</label><div class="flex items-center gap-2"><input v-model.number="form.price_low" type="number" min="0" class="field" /><span>至</span><input v-model.number="form.price_high" type="number" min="0" class="field" /></div></div><div><label class="label">成色 / 使用情况</label><input v-model="form.condition" class="field" /></div></div>
          <div class="mt-4"><label class="label">AI 评估标签（用顿号或逗号分隔）</label><input v-model="form.tags" class="field" /></div><div class="mt-4"><label class="label">校园带货文案</label><textarea v-model="form.description" class="field min-h-28 resize-y"></textarea></div>
          <div class="mt-4"><label class="label">联系方法 <span class="text-[#ed7546]">*</span></label><input v-model="form.contact" class="field" placeholder="微信号、QQ 号或手机号（请确认准确）" /></div>
          <div class="mt-6 flex flex-wrap gap-3"><button class="secondary" @click="analysis=null">重新上传图片</button><button class="primary flex-1" :disabled="publishSaving" @click="publish">{{ publishSaving ? '正在发布…' : '确认并发布到校园集市 →' }}</button></div>
        </div>
      </section>

      <section v-else class="mt-8">
        <div class="flex flex-wrap items-end justify-between gap-3"><div><span class="pill !bg-[#eaf7e7] !text-[#478149] !border-[#d7ebd4]">我的小铺</span><h1 class="section-title mt-3 text-3xl">你好，{{ user?.username }} 👋</h1><p class="mt-2 text-sm text-[#718b73]">在这里管理你发布的全部闲置商品。</p></div><button class="primary" @click="goPublish">＋ 发布新闲置</button></div>
        <div v-if="profileLoading" class="grid mt-7"><div v-for="i in 4" :key="i" class="skeleton"></div></div>
        <div v-else-if="myListings.length" class="grid mt-7"><article v-for="item in myListings" :key="item.id" class="card"><div class="relative cursor-pointer" @click="openDetail(item)"><img class="card-image" :src="image(item)" :alt="item.title" /><span v-if="item.status !== 'on_sale'" class="status">{{ item.status === 'sold' ? '已售出' : '已下架' }}</span></div><div class="p-3.5"><h3 class="line-clamp-1 font-bold text-[#334c37]">{{ item.title }}</h3><p class="mt-1 text-sm font-bold text-[#ed7546]">¥{{ item.price_low }} - {{ item.price_high }}</p><div class="mt-3 flex flex-wrap gap-2"><button v-if="item.status === 'on_sale'" class="secondary !px-2.5 !py-1.5 text-xs" @click="changeStatus(item, 'sold')">标记售出</button><button v-if="item.status !== 'on_sale'" class="secondary !px-2.5 !py-1.5 text-xs" @click="changeStatus(item, 'on_sale')">重新上架</button><button v-if="item.status !== 'off_shelf'" class="secondary !px-2.5 !py-1.5 text-xs" @click="changeStatus(item, 'off_shelf')">下架</button><button class="danger !px-2.5 !py-1.5 text-xs" @click="deleteListing(item)">删除</button></div></div></article></div>
        <div v-else class="empty mt-7"><div class="text-4xl">🏡</div><p class="mb-3 font-bold">你的小铺还没有商品</p><button class="primary" @click="goPublish">去发布第一件闲置</button></div>
      </section>
    </main>

    <div v-if="notice" class="fixed bottom-5 left-1/2 z-[80] -translate-x-1/2 rounded-xl px-4 py-3 text-sm font-bold shadow-lg" :class="noticeError ? 'bg-[#fff1ee] text-[#b84840]' : 'bg-[#eaf8e7] text-[#347438]'">{{ notice }}</div>

    <div v-if="showAuth" class="modal-wrap" @click.self="showAuth=false"><div class="modal max-w-[430px]"><div class="modal-header"><div><h2 class="font-extrabold text-[#355039]">{{ authMode === 'login' ? '欢迎回来' : '加入青柠校园集' }}</h2><p class="mt-1 text-xs text-[#809781]">{{ authMode === 'login' ? '登录后即可发布和管理闲置' : '注册一个账号，开始安心交易' }}</p></div><button class="icon-button" @click="showAuth=false">×</button></div><form class="modal-body" @submit.prevent="submitAuth"><label class="label">用户名</label><input v-model.trim="authForm.username" class="field" required minlength="3" maxlength="32" placeholder="字母、数字、下划线或短横线" /><label class="label mt-4">密码</label><input v-model="authForm.password" type="password" class="field" required minlength="6" placeholder="至少 6 位" /><p v-if="authError" class="notice error mt-4">{{ authError }}</p><button class="primary mt-5 w-full" type="submit">{{ authMode === 'login' ? '登录' : '注册并登录' }}</button><p class="mt-4 text-center text-sm text-[#6f896f]">{{ authMode === 'login' ? '还没有账号？' : '已经有账号？' }}<button class="ml-1 border-0 bg-transparent p-0 font-bold text-[#4a954a]" type="button" @click="authMode = authMode === 'login' ? 'register' : 'login'; authError=''">{{ authMode === 'login' ? '立即注册' : '去登录' }}</button></p></form></div></div>

    <div v-if="selectedItem" class="modal-wrap" @click.self="selectedItem=null"><div class="modal"><div class="modal-header"><div><span class="text-xs font-bold text-[#6b956c]">{{ selectedItem.category }} · {{ selectedItem.condition }}</span><h2 class="mt-1 font-extrabold text-[#355039]">{{ selectedItem.title }}</h2></div><button class="icon-button" @click="selectedItem=null">×</button></div><div class="modal-body"><div class="grid grid-cols-3 gap-3"><img v-for="url in selectedItem.image_urls" :key="url" class="preview" :src="url" :alt="selectedItem.title" /></div><div class="mt-5 flex flex-wrap items-center gap-2"><span v-for="tag in selectedItem.tags" :key="tag" class="tag">{{ tag }}</span><span v-if="selectedItem.status === 'sold'" class="rounded-md bg-orange-100 px-2 py-1 text-xs font-bold text-orange-600">已售出</span></div><p class="mt-4 text-2xl font-extrabold text-[#ed7546]">¥{{ selectedItem.price_low }} - {{ selectedItem.price_high }}</p><p class="mt-4 whitespace-pre-line leading-7 text-[#526d56]">{{ selectedItem.description }}</p><p class="mt-4 text-sm text-[#88a088]">发布于 {{ date(selectedItem.created_at) }} · 卖家：{{ selectedItem.owner }}</p><div class="mt-5 rounded-xl bg-[#f1f9ef] p-4"><p class="text-sm font-bold text-[#537657]">卖家联系方式</p><div class="mt-2 flex flex-wrap items-center justify-between gap-3"><strong class="select-all text-[#315d37]">{{ selectedItem.contact }}</strong><button class="primary !px-3 !py-2 text-sm" @click="copyContact">复制联系方法</button></div></div><div v-if="isOwner(selectedItem) || user?.is_admin" class="mt-5 flex flex-wrap gap-2 border-t border-[#edf2ec] pt-5"><button v-if="isOwner(selectedItem) && selectedItem.status === 'on_sale'" class="secondary" @click="changeStatus(selectedItem, 'sold')">标记已售出</button><button v-if="isOwner(selectedItem) && selectedItem.status !== 'off_shelf'" class="secondary" @click="changeStatus(selectedItem, 'off_shelf')">下架商品</button><button class="danger" @click="deleteListing(selectedItem)">{{ user?.is_admin && !isOwner(selectedItem) ? '管理员永久删除' : '永久删除商品' }}</button></div></div></div></div>
  </div>
</template>
