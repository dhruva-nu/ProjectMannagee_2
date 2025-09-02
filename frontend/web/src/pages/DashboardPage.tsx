import React, { useRef } from 'react';
import ChatBox, { type ChatBoxHandle } from '../components/ChatBox';
import IssueQuickAdd from '../components/IssueQuickAdd';

const DashboardPage: React.FC = () => {
  const chatRef = useRef<ChatBoxHandle>(null)

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
      <h1 className="text-4xl font-bold mb-8 text-primary-500">Welcome to your Dashboard!</h1>
      <p className="text-lg text-gray-300 mb-8">You are successfully logged in.</p>
      <IssueQuickAdd onInsertProject={handleInsertProject} onInsertIssue={handleInsertIssue} />
      <ChatBox ref={chatRef} />
    </div>
  );
};

export default DashboardPage;