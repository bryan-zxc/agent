# add text doc processing in planner
elif f.document_context.file_type == "text":
                        # Read the text file content using the stored encoding
                        try:
                            text_content = Path(f.filepath).read_text(
                                encoding=f.document_context.encoding
                            )
                            # Limit to first 1 million characters
                            limited_content = text_content[:1000000]
                            if len(text_content) > 1000000:
                                limited_content += "...\n\n[Content truncated to first 1 million characters]"

                            self.add_message(
                                role="user",
                                content=f"Text file `{Path(f.filepath).name}` contains the following content:\n\n{limited_content}",
                            )
                        except Exception as e:
                            self.add_message(
                                role="user",
                                content=f"Text file `{Path(f.filepath).name}` could not be read with encoding `{f.document_context.encoding}`. Error: {str(e)}",
                            )

# text doc handling and early data checking in router
async def _invoke_single(self, files: list[str]):
        file_list = []
        image_types = []
        data_types = []
        document_types = []
        unprocessed_files = []
        for f in files:
            if Path(f).suffix == ".csv":
                # Test CSV file readability before adding to file_list
                try:
                    duckdb.sql(
                        f"SELECT * FROM read_csv('{f}', strict_mode=false, all_varchar=true) LIMIT 100000"
                    )
                    file_list.append(
                        File(filepath=f, file_type="data", data_context="csv")
                    )
                    data_types.append("csv")
                except Exception as e:
                    logger.error(f"CSV file {f} cannot be read: {e}")
                    self.user_response.append(
                        f"The CSV file `{f}` cannot be processed due to format issues. "
                        f"Error: {str(e)[:250]}..."
                    )
                continue

            if Path(f).suffix == ".pdf":
                document_types.append("pdf")
                document_content = extract_document_content(f)
                doc_meta = create_document_meta_summary(document_content)
                is_image_pdf = await self.llm.a_get_response(
                    messages=[
                        {
                            "role": "developer",
                            "content": f"Based on the following document metadata, is the document likely an image based pdf?\n\n```json\n{doc_meta.model_dump_json(indent=2)}\n```",
                        }
                    ],
                    model=self.router_model,
                    temperature=self.router_temperature,
                    response_format=PDFType,
                )
                pdf_full = PDFFull(
                    filename=Path(f).name,
                    is_image_based=is_image_pdf.is_image_based,
                    content=document_content,
                    meta=doc_meta,
                )
                file_list.append(
                    File(
                        filepath=f,
                        file_type="document",
                        document_context=DocumentContext(
                            file_type="pdf",
                            pdf_content=pdf_full,
                        ),
                    )
                )
                continue

            # Try to read as text file with multiple encodings
            encodings_to_try = ["utf-8", "utf-16", "windows-1252"]
            text_processed = False
            for encoding in encodings_to_try:
                try:
                    Path(f).read_text(encoding=encoding)
                    file_list.append(
                        File(
                            filepath=f,
                            file_type="document",
                            document_context=DocumentContext(
                                file_type="text",
                                encoding=encoding,
                            ),
                        )
                    )
                    document_types.append("text")
                    text_processed = True
                    break  # Successfully read, exit the encoding loop
                except (UnicodeDecodeError, UnicodeError):
                    continue  # Try next encoding
                except OSError:
                    break  # File system error, don't try other encodings
            
            if text_processed:
                continue

            is_image_bool, error_message = is_image(f)
            if is_image_bool:
                from agent.tools import get_img_breakdown

                image_breakdown = get_img_breakdown(base64_image=encode_image(f))
                if image_breakdown.unreadable:
                    self.user_response.append(
                        f"\n\nThe image {f} cannot be read.\n\n{image_breakdown.image_quality}"
                    )
                else:
                    file_list.append(
                        File(
                            filepath=f,
                            file_type="image",
                            image_context=image_breakdown.elements,
                        )
                    )
                    image_types.extend(
                        [element.element_type for element in image_breakdown.elements]
                    )
                continue

            # If we reach here, the file was not processed
            unprocessed_files.append(f)

        # Add message for unprocessed files at the beginning of user_response
        if unprocessed_files:
            unprocessed_message = (
                f"Files not used are: {', '.join(unprocessed_files)}. "
                f"Under advanced mode, agent is activated and currently only accepts PDF, CSV, text and image files. "
                f"Please convert your file(s) to one of the above types, or alternatively switch to standard mode."
            )
            self.user_response.insert(0, unprocessed_message)

        data_types = list(set(data_types))
        image_types = list(set(image_types))
        document_types = list(set(document_types))
        instructions = []
        if image_types:
            instructions.extend(
                [
                    f"# Instructions for handling - {element_type} image:\n\n{INSTRUCTION_LIBRARY.get("image").get(element_type, "")}"
                    for element_type in image_types
                ]
            )
        if data_types:
            instructions.extend(
                [
                    f"# Instructions for handling - {data_type} data:\n\n{INSTRUCTION_LIBRARY.get("data").get(data_type, "")}"
                    for data_type in data_types
                ]
            )
        if document_types:
            instructions.extend(
                [
                    f"# Instructions for handling - {document_type} document:\n\n{INSTRUCTION_LIBRARY.get("document").get(document_type, "")}"
                    for document_type in document_types
                ]
            )

        if instructions:
            logging.info("Agentic response activated.")
            self.planner = PlannerAgent(
                user_question=self.user_question,
                instruction="\n\n---\n\n".join(instructions),
                files=file_list,
            )
            await self.planner.invoke()
            # user_response is now a simple string containing the markdown response
            self.user_response.append(self.planner.user_response)
        else:
            legacy_response = await legacy_get_answer(self.user_request)
            try:
                self.user_response.append(legacy_response.get("answer"))
            except Exception as e:
                self.legacy_response = legacy_response
