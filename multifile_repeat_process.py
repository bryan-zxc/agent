class FileGrouping(BaseModel):
    file_groups: list[list[str]] = Field(
        description="List of file groups. Each group is a list of file paths that should be processed together. "
        "By default, in case of doubt, there should only be one group with all the files in it. "
        "For example, files A, B, C and D should be grouped as [[A, B, C, D]]. "
        "However, if the user request is looking for multiple responses, one per file, the groupings should look like [[A], [B], [C], [D]]. "
        "If the user's request (for example) specifically asks for a file A to be referenced in actioning each of the other files B, C and D, the groups would be [[A, B], [A, C], [A, D]]. "
    )


    async def load_files(self):
        self.files = self.user_request.pattern.split(",")
        if not self.files:
            self.file_groups = []
        elif len(self.files) == 1:
            self.file_groups = [self.files]  # Single group with all files
        else:
            # Use LLM to determine file groupings
            file_grouping_response = await self.llm.a_get_response(
                messages=[
                    {
                        "role": "user",
                        "content": f"User question/request:\n\n{self.user_question}\n\nFiles: {', '.join(self.files)}",
                    },
                    {
                        "role": "developer",
                        "content": "Restructure the files to a list of groups of files that need to be processed one by one. "
                        "By default, in case of doubt, there should only be one group with all the files in it. "
                        "If the user's question indicates that they want to process files independently from each other, looking for one response per file (as opposed to a single response using all files), "
                        "then by default, each group should contain only one file unless there is evidence to suggest otherwise. "
                        "In the case where the user specifically instructs to repeatedly use a particular file (for example) when processing other files one by one, the groups should reflect that and have the file repeat across groups.",
                    },
                ],
                model="gpt-4.1-if-global",  # Use a specific model for file grouping
                temperature=self.router_temperature,
                response_format=FileGrouping,
            )
            self.file_groups = file_grouping_response.file_groups

    async def invoke(self):
        await self.load_files()
        for file_group in self.file_groups:
            await self._invoke_single(file_group)
