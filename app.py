from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_restful import Api, Resource
import os
import pika
import json

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////app/db/agua.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['RABBITMQ_HOST'] = os.getenv('RABBITMQ_HOST', 'rabbitmq')
app.config['RABBITMQ_QUEUE'] = 'notificacoes_agua'

db = SQLAlchemy(app)
api = Api(app)

class Medicao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(10), nullable=False)
    consumo = db.Column(db.Float, nullable=False)

def enviar_notificacao(mensagem):
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=app.config['RABBITMQ_HOST'],
                heartbeat=600,
                blocked_connection_timeout=300
            )
        )
        channel = connection.channel()
        # Garanta que a fila é declarada como durável
        channel.queue_declare(
            queue=app.config['RABBITMQ_QUEUE'],
            durable=True  # ← Isso persiste a fila entre reinícios
        )
        channel.basic_publish(
            exchange='',
            routing_key=app.config['RABBITMQ_QUEUE'],
            body=json.dumps(mensagem),
            properties=pika.BasicProperties(
                delivery_mode=2  # Torna a mensagem persistente
            )
        )
        print(f"✅ Mensagem enviada: {mensagem}")  # Log para debug
        connection.close()
    except Exception as e:
        print(f"❌ Erro no RabbitMQ: {str(e)}")

class MedicaoResource(Resource):
    def get(self):
        medicoes = Medicao.query.all()
        return {'medicoes': [{'id': m.id, 'data': m.data, 'consumo': m.consumo} for m in medicoes]}

    def post(self):
        try:
            data = request.get_json()
            if not data or 'data' not in data or 'consumo' not in data:
                return {'error': 'Campos obrigatórios faltando!'}, 400

            nova_medicao = Medicao(data=data['data'], consumo=data['consumo'])
            db.session.add(nova_medicao)
            db.session.commit()

            mensagem = {
                'tipo': 'nova_medicao',
                'dados': {
                    'id': nova_medicao.id,
                    'data': nova_medicao.data,
                    'consumo': nova_medicao.consumo
                }
            }
            enviar_notificacao(mensagem)

            return {'message': 'Medição adicionada com sucesso!', 'id': nova_medicao.id}, 201
        except Exception as e:
            return {'error': str(e)}, 500

api.add_resource(MedicaoResource, '/medicoes')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)