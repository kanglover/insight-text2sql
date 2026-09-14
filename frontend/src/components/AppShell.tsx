import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { systemApi } from '../api/endpoints'
import { Icon, type IconName } from './Icon'

interface MenuEntry {
  key: string
  label: string
  icon: IconName
  path: string
  children?: { key: string; label: string; path: string }[]
}

const MENU: MenuEntry[] = [
  { key: 'qa', label: '智能问数', icon: 'chat', path: '/' },
  {
    key: 'system',
    label: '系统管理',
    icon: 'settings',
    path: '/system',
    children: [
      { key: 'app', label: '应用配置', path: '/system/app' },
      { key: 'model', label: '模型配置', path: '/system/model' },
    ],
  },
  { key: 'logs', label: '日志', icon: 'logs', path: '/logs' },
  {
    key: 'feedback',
    label: '反馈管理',
    icon: 'flag',
    path: '/feedback',
    children: [{ key: 'review', label: '回复校对', path: '/feedback/review' }],
  },
]

export function AppShell() {
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const [openKeys, setOpenKeys] = useState<string[]>(['system', 'feedback'])
  const [menuOpen, setMenuOpen] = useState(false)
  const [health, setHealth] = useState<{ llm_provider: string; llm_configured: boolean } | null>(
    null,
  )

  // 顶栏展示「后端是否已配置模型」，避免用户以为是前端问题
  useEffect(() => {
    systemApi
      .health()
      .then((data) =>
        setHealth({ llm_provider: data.llm_provider, llm_configured: data.llm_configured }),
      )
      .catch(() => setHealth(null))
  }, [])

  useEffect(() => {
    setMenuOpen(false)
  }, [location.pathname])

  const isChildActive = (entry: MenuEntry) =>
    entry.children?.some((child) => location.pathname.startsWith(child.path)) ?? false

  return (
    <div className="app-layout" style={{ flexDirection: 'column' }}>
      <header className="top-bar">
        <div className="brand">
          <span className="brand-badge">
            <Icon name="chart" size={15} />
          </span>
          经管之星
          <span className="brand-sub">智能问数 · Text2SQL</span>
        </div>
        <div className="top-right">
          <button className="icon-btn" aria-label="消息">
            <Icon name="bell" size={17} />
          </button>
          <button className="icon-btn" aria-label="帮助">
            <Icon name="book" size={17} />
          </button>
          <div className="avatar-wrap">
            <button
              className="avatar"
              onClick={() => setMenuOpen((value) => !value)}
              aria-label="账号菜单"
            >
              管
            </button>
            {menuOpen ? (
              <div className="avatar-menu">
                <div className="am-row">
                  <strong>管理员</strong>
                  <span>本地演示账号</span>
                </div>
                <div className="am-divider" />
                <div className="am-row">
                  <strong>后端模型</strong>
                  <span>
                    {health
                      ? `${health.llm_provider} · ${health.llm_configured ? '已配置密钥' : '未配置密钥（将走规则引擎）'}`
                      : '无法连接后端'}
                  </span>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      <div className="app-body">
        <nav className={collapsed ? 'sidebar collapsed' : 'sidebar'}>
          <div className="sidebar-menu">
            {MENU.map((entry) => {
              const hasChildren = Boolean(entry.children?.length)
              const opened = openKeys.includes(entry.key)
              const active = hasChildren ? isChildActive(entry) : location.pathname === entry.path

              return (
                <div key={entry.key}>
                  {hasChildren ? (
                    <button
                      // 父级只做「高亮提示」，实心选中留给具体的子菜单项，
                      // 否则父子同时变成实心蓝，层级看起来是平的。
                      className={active ? 'menu-item parent-active' : 'menu-item'}
                      onClick={() =>
                        setOpenKeys((keys) =>
                          keys.includes(entry.key)
                            ? keys.filter((key) => key !== entry.key)
                            : [...keys, entry.key],
                        )
                      }
                      title={entry.label}
                    >
                      <Icon name={entry.icon} size={16} />
                      <span className="label">{entry.label}</span>
                      <span className={opened ? 'arrow open' : 'arrow'}>
                        <Icon name="chevronRight" size={13} />
                      </span>
                    </button>
                  ) : (
                    <NavLink
                      to={entry.path}
                      className={() => (active ? 'menu-item active' : 'menu-item')}
                      title={entry.label}
                    >
                      <Icon name={entry.icon} size={16} />
                      <span className="label">{entry.label}</span>
                    </NavLink>
                  )}

                  {hasChildren ? (
                    <div className={opened ? 'sub-menu open' : 'sub-menu'}>
                      {entry.children?.map((child) => (
                        <NavLink
                          key={child.key}
                          to={child.path}
                          className={() =>
                            location.pathname.startsWith(child.path)
                              ? 'menu-item active'
                              : 'menu-item'
                          }
                        >
                          <span className="label">{child.label}</span>
                        </NavLink>
                      ))}
                    </div>
                  ) : null}
                </div>
              )
            })}
          </div>

          <div className="sidebar-footer">
            <button onClick={() => setCollapsed((value) => !value)} aria-label="折叠侧栏">
              <Icon name="panelLeft" size={15} />
              {collapsed ? '' : '收起'}
            </button>
          </div>
        </nav>

        <main className="main-wrap">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
