export default function Status({ status }) { const labels = { completed: '已完成', running: '运行中', awaiting_human: '待审批', failed: '失败' }; return <span className={`status ${status}`}><i />{labels[status] || status}</span> }

