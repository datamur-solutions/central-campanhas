import threading
import time

from app.campaign_html_service import (
    publicar_html_campanha,
)


_locks = {}
_locks_guard = threading.Lock()


def _lock_campanha(
    codigo_campanha: str,
):
    codigo = (
        str(codigo_campanha)
        .strip()
        .upper()
    )

    with _locks_guard:
        if codigo not in _locks:
            _locks[codigo] = (
                threading.Lock()
            )

        return _locks[codigo]


def _publicar_com_retry(
    codigo_campanha: str,
):
    codigo = (
        str(codigo_campanha)
        .strip()
        .upper()
    )

    lock = _lock_campanha(
        codigo
    )

    with lock:
        ultimo_erro = None

        for tentativa in range(
            1,
            4,
        ):
            try:
                resultado = (
                    publicar_html_campanha(
                        codigo
                    )
                )

                print(
                    "[HTML]",
                    codigo,
                    "atualizado automaticamente:",
                    resultado.get(
                        "caminho"
                    ),
                )

                return

            except Exception as erro:
                ultimo_erro = erro

                print(
                    "[HTML]",
                    codigo,
                    f"tentativa {tentativa}/3 falhou:",
                    str(erro),
                )

                if tentativa < 3:
                    time.sleep(
                        2 * tentativa
                    )

        print(
            "[HTML]",
            codigo,
            "não pôde ser atualizado após 3 tentativas.",
            "A operação principal da campanha foi preservada.",
            "Erro:",
            str(ultimo_erro),
        )


def atualizar_html_em_background(
    codigo_campanha: str,
):
    """
    Atualiza o HTML sem bloquear a resposta do Portal.
    Se o SharePoint/Power Automate estiver indisponível,
    a movimentação da campanha continua normalmente.
    """

    if not codigo_campanha:
        return

    thread = threading.Thread(
        target=_publicar_com_retry,
        args=(
            str(codigo_campanha),
        ),
        daemon=True,
        name=(
            "html-"
            + str(
                codigo_campanha
            )
        ),
    )

    thread.start()
