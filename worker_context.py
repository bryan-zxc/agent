class TaskResponseModel(BaseModel):
    task_id: str = Field(description="The ID of the completed task")
    task_description: str = Field(
        description="Description of the task that was executed"
    )
    task_status: str = Field(
        description="Status of the task (completed, failed validation, etc.)"
    )
    assistance_responses: str = Field(
        description="The assistant responses from the worker during task execution"
    )

#code in planner
async def _update_execution_plan_after_task(self):
        """
        Updates the execution plan using Pydantic models.
        """
        t = self.task_queue.completed_task
        worker = self.task_queue.workers.get(t.task_id)
        worker_assistant_messages = ""
        if worker and hasattr(worker, "messages"):
            assistant_messages = [
                msg["content"]
                for msg in worker.messages
                if msg.get("role") == "assistant"
            ]
            worker_assistant_messages = "\n\n---\n\n".join(assistant_messages)

        # Add a message to the conversation history about the completed task
        task_completion_msg = (
            f"# Responses from worker\n\n"
            f"**Task ID**: {t.task_id}\n\n"
            f"**Task Description**: {t.task_description}\n\n"
            f"**Task Status**: {t.task_status}\n\n"
            f"**Worker Responses**:\n\n{worker_assistant_messages}"
        )
        self.add_message(
            role="assistant",
            content=task_completion_msg,
        )

        # Append to task_responses list
        task_response = TaskResponseModel(
            task_id=t.task_id,
            task_description=t.task_description,
            task_status=t.task_status,
            assistance_responses=worker_assistant_messages,
        )
        self.task_responses.append(task_response)

# code in worker
async def invoke(self):
        appending_msgs = []

        if self.task.input_variables:
            appending_msgs.append(
                {
                    "role": "developer",
                    "content": "The following variables are available for use, they already exist in the environment, "
                    f"you do not need to declare or create it: {', '.join(self.task.input_variables.keys())}",
                }
            )

        # Add latest 10 task responses if available
        if self.task_responses:
            latest_responses = self.task_responses[-10:]  # Get latest 10 items
            responses_content = "\n\n---\n\n".join(
                [response.model_dump_json(indent=2) for response in latest_responses]
            )
            appending_msgs.append(
                {
                    "role": "developer",
                    "content": f"For additional context, the detailed outcomes of the previous 10 tasks are as follows:\n\n{responses_content}",
                }
            )

        for n in range(self.max_retry):
            logging.info(f"Worker {self.task.task_id} - Attempt {n + 1}")
            task_result = await self.llm.a_get_response(
                messages=self.messages + appending_msgs,
                model=self.model,
                temperature=self.temperature,
                response_format=TaskArtefact,
            )
