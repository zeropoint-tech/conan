pipeline {

  agent any

  stages {
	  stage('Conan configuration') {
      steps {
        rtConanClient (id: "myConanClient")
        rtConanRemote (
          name: "artifactory",
          serverId: "artifactory",
          repo: "conan-local",
          clientId: "myConanClient",
        )
      }
    }

    stage('Export recipies') {
      steps {
        rtBuildInfo(
          captureEnv: true,
        )
        rtConanRun(
          clientId: "myConanClient",
          command: "export semver"
        )
        rtConanRun(
          clientId: "myConanClient",
          command: "upload -r artifactory semver --all --confirm"
        )
        rtPublishBuildInfo (
          serverId: "artifactory"
        )
      }
    }
  }
}
