const readStream = async (stream: ReadableStream) => {
  const reader = stream.getReader()
  const { value } = await reader.read()
  return new TextDecoder().decode(value)
}

/**
 * 读取流中的json数据
 * @param stream
 * @returns json or { text: bodyText, error }
 */
export const readJsonFromStream = async (stream: ReadableStream) => {
  const bodyText = await readStream(stream)
  try {
    return {
      data: JSON.parse(bodyText),
      error: null,
    }
  }
  catch (error) {
    return { data: bodyText, error }
  }
}
