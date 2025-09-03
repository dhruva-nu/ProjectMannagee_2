import React, { useRef, useState, useEffect } from 'react';
import ChatBox, { type ChatBoxHandle, type ChatUiMessage } from '../components/ChatBox';
import IssueQuickAdd from '../components/IssueQuickAdd';
import JiraStatus from '../components/JiraStatus';
import SprintStatus from '../components/SprintStatus';

const DashboardPage: React.FC = () => {
  const chatRef = useRef<ChatBoxHandle>(null)
  const [latestUi, setLatestUi] = useState<ChatUiMessage | null>(null)
  const [animationKey, setAnimationKey] = useState(0)

  useEffect(() => {
    if (latestUi) {
      setAnimationKey(prevKey => prevKey + 1)
    }
  }, [latestUi])

  const handleInsertProject = (projectKey: string) => {
    const pk = projectKey.trim()
    if (!pk) return
    chatRef.current?.insertText(`@${pk}`)
  }

  const handleInsertIssue = (issueKey: string) => {
    const ik = issueKey.trim()
    if (!ik) return
    chatRef.current?.insertText(`@${ik}`)
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-secondary-800 text-white p-8 font-sans">
      {!latestUi && (
        <>
          <h1 className="text-4xl font-bold mb-8 text-primary-500">Welcome to your Dashboard!</h1>
          <p className="text-lg text-gray-300 mb-8">You are successfully logged in.</p>
        </>
      )}

      <IssueQuickAdd onInsertProject={handleInsertProject} onInsertIssue={handleInsertIssue} />

      {latestUi && (
        <div className="w-full max-w-[500px] mt-6">
          {latestUi.type === 'jira_status' ? (
            <JiraStatus key={animationKey} data={latestUi.data} />
          ) : latestUi.type === 'sprint_status' ? (
            <SprintStatus data={latestUi.data} />
          ) : null}
        </div>
      )}

      <ChatBox ref={chatRef} onUiMessage={setLatestUi} />
    </div>
  );
};

export default DashboardPage;