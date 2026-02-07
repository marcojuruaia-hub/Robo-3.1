import os
import time
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OpenOrderParams
from py_clob_client.order_builder.constants import SELL

print("=" * 60)
print(">>> 🤖 ROBÔ DE VENDAS - VERSÃO SIMPLIFICADA <<<")
print("=" * 60)

# ============================================================================
# ⚙️ CONFIGURAÇÃO FÁCIL (EDITA SÓ AQUI)
# ============================================================================
CONFIG = {
    "NOME": "VENDAS-AUTO",
    "TOKEN_ID": "64141243045079364243337150943335853200535056280589013247663317689482853573098",
    "PROXY": "0x658293eF9454A2DD555eb4afcE6436aDE78ab20B",
    
    # 🔽 AJUSTE SÓ ESSES 3 VALORES 🔽
    "PRECO_MAXIMO": 0.99,      # Ex: 0.40 = R$ 0,40
    "PRECO_MINIMO": 0.61,      # Ex: 0.20 = R$ 0,20
    "INTERVALO_PRECO": 0.01,   # Espaço entre preços (0.01 = 1 centavo)
    
    # 🔽 CONFIGURAÇÕES PADRÃO 🔽
    "SHARES_POR_ORDEM": 5,     # Quantidade por ordem
    "INTERVALO_TEMPO": 10,     # Tempo entre ciclos (segundos)
}
# ============================================================================

def criar_grid_vendas(config):
    """Cria automaticamente a lista de preços"""
    preco_max = config["PRECO_MAXIMO"]
    preco_min = config["PRECO_MINIMO"]
    intervalo = config["INTERVALO_PRECO"]
    
    # Gera preços do MAIOR para o MENOR
    preco_atual = preco_max
    grid = []
    
    while preco_atual >= preco_min:
        grid.append(round(preco_atual, 2))
        preco_atual -= intervalo
    
    return grid

def main():
    # 1. Cria grid automaticamente
    CONFIG["GRID"] = criar_grid_vendas(CONFIG)
    
    print(f"🔧 CONFIGURAÇÃO:")
    print(f"   Nome: {CONFIG['NOME']}")
    print(f"   Preços: ${CONFIG['PRECO_MAXIMO']} até ${CONFIG['PRECO_MINIMO']}")
    print(f"   Intervalo: {CONFIG['INTERVALO_TEMPO']}s")
    print(f"   Grid gerada: {len(CONFIG['GRID'])} preços")
    print(f"   Exemplo: {CONFIG['GRID'][:3]}...{CONFIG['GRID'][-3:]}")
    print("-" * 50)
    
    # 2. Conecta ao Polymarket
    key = os.getenv("PRIVATE_KEY")
    if not key:
        print("❌ ERRO: PRIVATE_KEY não configurada!")
        print("   Railway: Adicione como variável de ambiente")
        print("   Local: Execute: export PRIVATE_KEY=sua_chave")
        return
    
    try:
        client = ClobClient(
            "https://clob.polymarket.com/",
            key=key,
            chain_id=137,
            signature_type=2,
            funder=CONFIG["PROXY"]
        )
        client.set_api_creds(client.create_or_derive_api_creds())
        print("✅ Conectado ao Polymarket!")
    except Exception as e:
        print(f"❌ Falha na conexão: {e}")
        return
    
    # 3. Loop principal
    ciclo = 0
    ordens_criadas = []
    
    try:
        while True:
            ciclo += 1
            
            print(f"\n{'='*50}")
            print(f"🔄 CICLO {ciclo} - {time.strftime('%H:%M:%S')}")
            print(f"{'='*50}")
            
            # Verifica ordens ativas
            ordens_ativas = []
            try:
                todas_ordens = client.get_orders(OpenOrderParams())
                for ordem in todas_ordens:
                    if (ordem.get('asset_id') == CONFIG["TOKEN_ID"] and
                        ordem.get('status') == 'open' and
                        ordem.get('side') == 'SELL'):
                        
                        preco = round(float(ordem.get('price', 0)), 2)
                        ordens_ativas.append(preco)
                
                print(f"📊 Ordens ativas: {len(ordens_ativas)}")
                if ordens_ativas:
                    print(f"   Preços: {sorted(ordens_ativas, reverse=True)[:5]}...")
            except Exception as e:
                print(f"⚠️ Erro ao ver ordens: {e}")
            
            # Tenta criar próxima ordem
            ordem_criada = False
            sem_saldo = False
            
            for preco in CONFIG["GRID"]:
                if preco not in ordens_ativas and preco not in ordens_criadas:
                    print(f"\n🎯 Tentando criar ordem a ${preco:.2f}...")
                    
                    try:
                        ordem = OrderArgs(
                            price=preco,
                            size=CONFIG["SHARES_POR_ORDEM"],
                            side=SELL,
                            token_id=CONFIG["TOKEN_ID"]
                        )
                        
                        client.create_and_post_order(ordem)
                        ordens_criadas.append(preco)
                        print(f"✅ SUCESSO! {CONFIG['SHARES_POR_ORDEM']} shares a ${preco:.2f}")
                        ordem_criada = True
                        break
                        
                    except Exception as e:
                        erro = str(e).lower()
                        if "balance" in erro or "insufficient" in erro:
                            print(f"💰 Sem saldo para ${preco:.2f}")
                            sem_saldo = True
                            break
                        elif "already" in erro or "duplicate" in erro:
                            print(f"⏭️ Já existe ordem a ${preco:.2f}")
                            ordens_criadas.append(preco)
                        else:
                            print(f"⚠️ Erro: {e}")
            
            # Mostra resumo
            print(f"\n📋 RESUMO:")
            print(f"   Ciclo: {ciclo}")
            print(f"   Ordens criadas: {len(ordens_criadas)}")
            
            if ordens_criadas:
                print(f"   Preços: {sorted(ordens_criadas, reverse=True)}")
            
            if sem_saldo:
                print(f"   ⏹️ Sem saldo - aguardando...")
            elif not ordem_criada:
                print(f"   ✅ Todas ordens já criadas")
            
            # Aguarda próximo ciclo
            print(f"\n⏳ Próximo ciclo em {CONFIG['INTERVALO_TEMPO']}s...")
            time.sleep(CONFIG["INTERVALO_TEMPO"])
            
    except KeyboardInterrupt:
        print(f"\n\n🛑 Robô parado pelo usuário")
        print(f"   Total de ciclos: {ciclo}")
        print(f"   Ordens criadas: {len(ordens_criadas)}")
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
