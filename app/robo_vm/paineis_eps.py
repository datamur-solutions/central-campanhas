"""
PAINEIS DAS EPS - conector dos paineis operacionais dos parceiros

Na versao em producao, este modulo le o funil operacional
(tentativas, alo, efetivo, vendas) e as tabulacoes de Pos e
Profissionalizantes direto dos paineis de cada EPS, por API com
login guardado no cofre do Windows (keyring).

Na versao publica do portfolio o conector foi omitido: ele
depende de sistemas de terceiros. A interface e mantida para o
robo rodar sem alteracao; a conferencia com o painel apenas
fica registrada como indisponivel.

As matriculas NUNCA vem daqui: a fonte oficial e o Databricks.
"""

OMITIDO = "Conector de painel de parceiro omitido na versão pública."


class Paineis:
    def apurar(self, produto, escopos, p, usa_mailing, ini, fim):
        """(funil | None, tabulacoes, observacao)."""
        return None, [], OMITIDO
