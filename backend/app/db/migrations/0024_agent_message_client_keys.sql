ALTER TABLE agent_messages
ADD COLUMN client_message_key TEXT;

CREATE UNIQUE INDEX idx_agent_messages_conversation_client_key
ON agent_messages(conversation_id, client_message_key)
WHERE client_message_key IS NOT NULL;
