import base64
import os
from zhipuai import ZhipuAI

# Configuração da chave API
# Substitua "asdf" pela sua chave real se necessário, 
# embora "asdf" pareça ser um exemplo fictício.
API_KEY = "ac9fe718351e48abbadf75881c35a58f.6FlbDNYfaWHdoNkJ"

def reconhecer_caracteres_imagem(caminho_imagem):
    client = ZhipuAI(api_key=API_KEY)
    
    # Verifica se o arquivo existe
    if not os.path.exists(caminho_imagem):
        print(f"Erro: O arquivo '{caminho_imagem}' não foi encontrado.")
        return

    # Abre a imagem e converte para base64
    with open(caminho_imagem, 'rb') as image_file:
        image_base64 = base64.b64encode(image_file.read()).decode('utf-8')
    
    print("Enviando imagem para reconhecimento...")

    try:
        # Chamada para o modelo de visão GLM-4V-Flash
        response = client.chat.completions.create(
            model="glm-4v-flash",  # Modelo de visão Flash
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_base64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": "Por favor, extraia e reconheça todos os caracteres de texto visíveis nesta imagem. Liste-os exatamente como aparecem."
                        }
                    ]
                }
            ],
            top_p=0.1,
            temperature=0.1,
            max_tokens=1024,
            stream=False
        )
        
        # Imprimindo o resultado
        texto_reconhecido = response.choices[0].message.content
        print("-" * 30)
        print("Texto Reconhecido:")
        print(texto_reconhecido)
        print("-" * 30)
        
        return texto_reconhecido

    except Exception as e:
        print(f"Ocorreu um erro na chamada da API: {e}")

# --- Execução ---
# Substitua 'minha_imagem.jpg' pelo caminho da sua imagem
if __name__ == "__main__":
    # Crie um arquivo de imagem fictício ou use um existente para testar
    caminho_da_imagem = "img.png" 
    
    reconhecer_caracteres_imagem(caminho_da_imagem)