import { Fragment, useState } from 'react'
import { useContext } from 'use-context-selector'
import { useTranslation } from 'react-i18next'
import { Menu, MenuButton, MenuItems, Transition } from '@headlessui/react'
import { RiAddLine, RiArrowDownSLine, RiDeleteBinLine } from '@remixicon/react'
import { readJsonFromStream } from '@/utils/read-stream'
import cn from '@/utils/classnames'
import { basePath } from '@/utils/var'
import PlanBadge from '@/app/components/header/plan-badge'
import { createWorkspace, deleteWorkspace, switchWorkspace } from '@/service/common'
import { useWorkspacesContext } from '@/context/workspace-context'
import { ToastContext } from '@/app/components/base/toast'
import type { Plan } from '@/app/components/billing/type'
import Modal from '@/app/components/base/modal'
import Button from '@/app/components/base/button'

const WorkplaceSelector = () => {
  const { t } = useTranslation()
  const { notify } = useContext(ToastContext)
  const { workspaces } = useWorkspacesContext()
  const currentWorkspace = workspaces.find(v => v.current)
  const [isCreating, setIsCreating] = useState(false)
  const [newWorkspaceName, setNewWorkspaceName] = useState('')
  const [loading, setLoading] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [workspaceToDelete, setWorkspaceToDelete] = useState<{ id: string; name: string } | null>(null)

  const handleSwitchWorkspace = async (tenant_id: string) => {
    try {
      if (currentWorkspace?.id === tenant_id)
        return
      await switchWorkspace({ url: '/workspaces/switch', body: { tenant_id } })
      notify({ type: 'success', message: t('common.actionMsg.modifiedSuccessfully') })
      location.assign(`${location.origin}${basePath}`)
    }
    catch {
      notify({ type: 'error', message: t('common.provider.saveFailed') })
    }
  }

  const handleCreateWorkspace = async () => {
    if (!newWorkspaceName.trim()) {
      notify({ type: 'error', message: t('common.userProfile.workspace') + t('common.actionMsg.nameRequired') })
      return
    }

    try {
      setLoading(true)
      let createWorkSpaceRst = { id: '' }
      try {
        createWorkSpaceRst = await createWorkspace({
          url: '/workspaces/create',
          body: { name: newWorkspaceName.trim() },
        })
      }
      catch (error: { body: ReadableStream } | any) {
        const { error: err, data } = await readJsonFromStream(error.body)
        if (!err) {
          const { code } = data || {}
          if (code === 'exceed_max_workspaces')
            notify({ type: 'error', message: t('common.actionMsg.createFailedExceed') })
        }
        return
      }
      notify({ type: 'success', message: t('common.actionMsg.createdSuccessfully') })
      // 切换到新创建的工作空间
      await switchWorkspace({ url: '/workspaces/switch', body: { tenant_id: createWorkSpaceRst.id } })
      location.assign(`${location.origin}`)
    }
    catch (error) {
      notify({ type: 'error', message: t('common.actionMsg.createFailed') })
    }
    finally {
      setLoading(false)
      setIsCreating(false)
      setNewWorkspaceName('')
    }
  }

  const handleDeleteWorkspace = async () => {
    if (!workspaceToDelete) return

    try {
      setLoading(true)
      await deleteWorkspace({
        url: '/workspaces/delete',
        body: { workspace_id: workspaceToDelete.id },
      })
      notify({ type: 'success', message: t('common.actionMsg.deletedSuccessfully') })
      location.assign(`${location.origin}`) // 刷新页面以更新工作空间列表
    }
    catch (error: { body: ReadableStream } | any) {
      notify({ type: 'error', message: t('common.actionMsg.deleteFailed') })
    }
    finally {
      setLoading(false)
      setIsDeleting(false)
      setWorkspaceToDelete(null)
    }
  }

  const showDeleteConfirm = (workspace: { id: string; name: string }) => {
    setWorkspaceToDelete(workspace)
    setIsDeleting(true)
  }

  return (
    <>
      <Menu as="div" className="relative h-full w-full">
        {({ open }) => (
          <>
            <MenuButton className={cn(
              `
                group flex w-full cursor-pointer items-center
                gap-1.5 p-0.5 hover:bg-state-base-hover ${open && 'bg-state-base-hover'} rounded-[10px]
              `,
            )}>
              <div className='flex h-6 w-6 items-center justify-center rounded-md bg-components-icon-bg-blue-solid text-[13px]'>
                <span className='h-6 bg-gradient-to-r from-components-avatar-shape-fill-stop-0 to-components-avatar-shape-fill-stop-100 bg-clip-text align-middle font-semibold uppercase leading-6 text-shadow-shadow-1 opacity-90'>{currentWorkspace?.name[0]?.toLocaleUpperCase()}</span>
              </div>
              <div className='flex flex-row'>
                <div className={'system-sm-medium max-w-[160px] truncate text-text-secondary'}>{currentWorkspace?.name}</div>
                <RiArrowDownSLine className='h-4 w-4 text-text-secondary' />
              </div>
            </MenuButton>
            <Transition
              as={Fragment}
              enter="transition ease-out duration-100"
              enterFrom="transform opacity-0 scale-95"
              enterTo="transform opacity-100 scale-100"
              leave="transition ease-in duration-75"
              leaveFrom="transform opacity-100 scale-100"
              leaveTo="transform opacity-0 scale-95"
            >
              <MenuItems
                className={cn(
                  `
                    shadows-shadow-lg absolute left-[-15px] mt-1 flex max-h-[400px] w-[280px] flex-col items-start overflow-y-auto rounded-xl
                    bg-components-panel-bg-blur backdrop-blur-[5px]
                  `,
                )}
              >
                <div className="flex w-full flex-col items-start self-stretch rounded-xl border-[0.5px] border-components-panel-border p-1 pb-2 shadow-lg ">
                  <div className='flex items-start self-stretch px-3 pb-0.5 pt-1'>
                    <span className='system-xs-medium-uppercase flex-1 text-text-tertiary'>{t('common.userProfile.workspace')}</span>
                  </div>
                  {
                    workspaces.map(workspace => (
                      <div className='flex items-center gap-2 self-stretch'>
                        <div className='flex flex-1 items-center gap-2 self-stretch rounded-lg py-1 pl-3 pr-2 hover:bg-state-base-hover' key={workspace.id} onClick={() => handleSwitchWorkspace(workspace.id)}>
                            <div className='flex h-6 w-6 items-center justify-center rounded-md bg-components-icon-bg-blue-solid text-[13px]'>
                              <span className='h-6 bg-gradient-to-r from-components-avatar-shape-fill-stop-0 to-components-avatar-shape-fill-stop-100 bg-clip-text align-middle font-semibold uppercase leading-6 text-shadow-shadow-1 opacity-90'>{workspace?.name[0]?.toLocaleUpperCase()}</span>
                            </div>
                            <div className='system-md-regular line-clamp-1 grow cursor-pointer overflow-hidden text-ellipsis text-text-secondary'>{workspace.name}</div>
                            <PlanBadge plan={workspace.plan as Plan} />
                        </div>
                        {/* 只有不是当前工作空间且用户是所有者才显示删除按钮 */}
                        {!workspace.current && workspace.role === 'owner' && (
                          <div
                            className="mr-2 cursor-pointer text-gray-500 hover:text-red-500"
                            onClick={() => showDeleteConfirm({ id: workspace.id, name: workspace.name })}
                          >
                            <RiDeleteBinLine className="h-4 w-4" />
                          </div>
                        )}
                      </div>
                    ))
                  }
                  <div
                    className='mt-2 flex items-center gap-2 self-stretch rounded-lg py-1 pl-3 pr-2 text-primary-600 hover:bg-state-base-hover'
                    onClick={() => setIsCreating(true)}
                  >
                    <RiAddLine className='h-5 w-5' />
                    <div className='system-md-medium cursor-pointer'>{t('common.userProfile.createWorkspace')}</div>
                  </div>
                </div>
              </MenuItems>
            </Transition>
          </>
        )}
      </Menu>

      {/* 创建工作空间模态框 */}
      {isCreating && (
        <Modal
          isShow={isCreating}
          onClose={() => {
            setIsCreating(false)
            setNewWorkspaceName('')
          }}
          title={t('common.userProfile.createWorkspace')}
          className='!w-[480px]'
        >
          <div className='mt-2'>
            <div className='mb-2 text-sm font-medium text-text-primary'>{t('common.userProfile.workspaceName')}</div>
            <input
              type="text"
              className='border-components-form-input-border bg-components-form-input-bg focus:border-components-form-input-focus-border block w-full rounded-lg border px-3 py-2 text-sm text-text-primary outline-none'
              placeholder={t('common.userProfile.workspaceNamePlaceholder')}
              value={newWorkspaceName}
              onChange={e => setNewWorkspaceName(e.target.value)}
              maxLength={50}
            />
          </div>
          <div className='mt-8 flex justify-end gap-2'>
            <Button
              className='w-20 !text-sm'
              onClick={() => {
                setIsCreating(false)
                setNewWorkspaceName('')
              }}
            >
              {t('common.operation.cancel')}
            </Button>
            <Button
              className='w-20 !text-sm'
              variant='primary'
              disabled={!newWorkspaceName.trim()}
              onClick={handleCreateWorkspace}
              loading={loading}
            >
              {t('common.operation.create')}
            </Button>
          </div>
        </Modal>
      )}

      {/* 删除工作空间确认模态框 */}
      {isDeleting && workspaceToDelete && (
        <Modal
          isShow={isDeleting}
          onClose={() => {
            setIsDeleting(false)
            setWorkspaceToDelete(null)
          }}
          title={t('common.userProfile.deleteWorkspace')}
          className='!w-[480px]'
        >
          <div className='mt-2'>
            <div className='text-sm text-text-primary'>
              {t('common.userProfile.deleteWorkspaceConfirm', { name: workspaceToDelete.name })}
            </div>
          </div>
          <div className='mt-8 flex justify-end gap-2'>
            <Button
              className='w-20 !text-sm'
              onClick={() => {
                setIsDeleting(false)
                setWorkspaceToDelete(null)
              }}
            >
              {t('common.operation.cancel')}
            </Button>
            <Button
              className='w-20 !text-sm'
              variant='primary'
              destructive
              onClick={handleDeleteWorkspace}
              loading={loading}
              disabled={loading}
            >
              {t('common.operation.delete')}
            </Button>
          </div>
        </Modal>
      )}
    </>
  )
}

export default WorkplaceSelector
